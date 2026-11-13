"""Étapes 3, 5 et 6 — classement, génération, vérification (synchrone ou par lots)."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .config import REPO_ROOT, Config
from .fulltext import select_sections
from .llm import LLM, Req
from .models import Candidate, GeneratedContent, Paper, RankBatch, Ranked, Verification

log = logging.getLogger(__name__)
PROMPTS = REPO_ROOT / "prompts"


@dataclass
class Article:
    """Un article prêt pour la génération : texte récupéré, éventuellement réduit aux sections utiles."""

    paper: Paper
    text: str
    source: str  # html | latex | pdf | abstract
    truncated: bool = False
    mode: str = "full"  # full | sections (ce qui a réellement été envoyé)


@dataclass
class Outcome:
    content: GeneratedContent
    status: str  # verified | unverified
    prompt_version: str
    corrected: bool = False  # True si une correction a été demandée après la 1re vérification
    checks: list[Verification] = field(default_factory=list)


def make_article(paper: Paper, text: str, source: str, truncated: bool, mode: str) -> Article:
    if mode == "sections" and source in ("html", "latex"):
        reduced, ok = select_sections(text)
        if ok:
            return Article(paper, reduced, source, truncated, "sections")
    return Article(paper, text, source, truncated, "full")


def load_prompt(name: str, prompts_dir: Path = PROMPTS) -> tuple[str, str]:
    """Renvoie (texte, version) ; la version est l'empreinte du fichier."""
    text = (prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()[:10]


def render(template: str, **values: str) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template.strip()


def _source_note(art: Article) -> str:
    note = {
        "html": "full text",
        "latex": "full LaTeX source",
        "pdf": "text extracted from the PDF; equations may be garbled",
        "abstract": "ABSTRACT ONLY, the full text was not available",
    }[art.source]
    if art.mode == "sections":
        note = "abstract, introduction, results and discussion/conclusion sections only; other sections were left out"
    return note + ("; the text was cut at a length limit and its end is missing" if art.truncated else "")


def _article_block(text: str, ttl: str) -> dict:
    """Le texte de l'article est le préfixe commun à la génération, à la vérification
    et à leurs corrections : c'est lui qu'on met en cache."""
    block: dict = {"type": "text", "text": f"<paper>\n{text}\n</paper>"}
    if ttl == "5m":
        block["cache_control"] = {"type": "ephemeral"}
    elif ttl == "1h":
        block["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
    return block


def _ttl(cfg: Config, batch: bool) -> str:
    return cfg.cache.batch_ttl if batch else cfg.cache.sync_ttl


# ---------- Étape 3 : classement ----------


def rank(llm: LLM, candidates: list[Candidate], cfg: Config) -> list[Ranked]:
    system, _ = load_prompt("system")
    template, _ = load_prompt("rank")
    levels = "\n".join(f"- {k}: {v}" for k, v in cfg.profile.levels.items()) or "(none specified)"
    by_id = {c.paper.arxiv_id: c for c in candidates}
    ranked: list[Ranked] = []
    size = cfg.models.rank_batch_size
    for i in range(0, len(candidates), size):
        batch = candidates[i : i + size]
        papers = "\n\n".join(
            f"arxiv_id: {c.paper.arxiv_id}{' [exploration]' if c.slot == 'exploration' else ''}\n"
            f"categories: {', '.join(c.paper.categories)}\n"
            f"title: {c.paper.title}\n"
            f"abstract: {c.paper.abstract}"
            for c in batch
        )
        prompt = render(template, interests=cfg.profile.interests.strip(), levels=levels, papers=papers)
        out = llm.run(Req(step="rank", model=cfg.models.rank, system=system, content=prompt, schema=RankBatch))
        got = set()
        for item in out.items:
            if item.arxiv_id in by_id and item.arxiv_id not in got:
                got.add(item.arxiv_id)
                ranked.append(Ranked(candidate=by_id[item.arxiv_id], rank=item))
        missing = {c.paper.arxiv_id for c in batch} - got
        if missing:
            log.warning("classement: %d articles sans note (%s)", len(missing), ", ".join(sorted(missing)))
    return ranked


# ---------- Étape 5 : génération ----------


def _tag(art: Article, label: str) -> dict:
    return {"arxiv_id": art.paper.arxiv_id, "label": label, "mode": art.mode}


def gen_req(art: Article, cfg: Config, *, batch: bool = False, feedback: str = "", label: str = "") -> tuple[Req, str]:
    """Requête de génération et version du prompt. `feedback` : corrections du vérificateur."""
    system, _ = load_prompt("system")
    template, version = load_prompt("generate")
    paper = art.paper
    fb = (
        "A reviewer checked your previous entry against the paper and found problems. "
        "Write the entry again with these corrected, removing anything the paper does not support:\n" + feedback
        if feedback
        else ""
    )
    prompt = render(
        template,
        source_note=_source_note(art),
        title=paper.title,
        authors=", ".join(paper.authors[:12]) + (" et al." if len(paper.authors) > 12 else ""),
        arxiv_id=paper.arxiv_id,
        categories=", ".join(paper.categories),
        level=cfg.profile.levels.get(paper.primary_category, "intermediate"),
        feedback=fb,
    )
    req = Req(
        step="generate",
        model=cfg.models.generate,
        system=system,
        content=[_article_block(art.text, _ttl(cfg, batch)), {"type": "text", "text": prompt}],
        schema=GeneratedContent,
        tag=_tag(art, label),
    )
    return req, version


# ---------- Étape 6 : vérification ----------


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def missing_quotes(content: GeneratedContent, text: str) -> list[str]:
    """Citations des claims introuvables telles quelles dans le texte (contrôle sans IA)."""
    hay = _norm(text)
    return [c.quote for c in content.claims if _norm(c.quote) not in hay]


def verify_req(art: Article, content: GeneratedContent, cfg: Config, *, batch: bool = False, label: str = "") -> Req:
    system, _ = load_prompt("system")
    template, _ = load_prompt("verify")
    missing = missing_quotes(content, art.text)
    quote_check = (
        "An exact string search did not find these supporting quotes in the paper. "
        "They may be paraphrased, differ only in formatting, or be invented; check each one:\n"
        + "\n".join(f"- {q}" for q in missing)
        if missing
        else ""
    )
    prompt = render(
        template,
        source_note=_source_note(art),
        quote_check=quote_check,
        entry=content.model_dump_json(indent=2),
    )
    return Req(
        step="verify",
        model=cfg.models.verify,
        system=system,
        content=[_article_block(art.text, _ttl(cfg, batch)), {"type": "text", "text": prompt}],
        schema=Verification,
        tag=_tag(art, label),
    )


# ---------- Génération + vérification ----------


def generate_verified(llm: LLM, art: Article, cfg: Config, label: str = "") -> Outcome:
    """Mode synchrone : génère puis vérifie ; une correction si la vérification échoue.

    Les appels d'un même article se suivent, pour profiter du cache de 5 minutes.
    """
    req, version = gen_req(art, cfg, label=label)
    content = llm.run(req)
    check = llm.run(verify_req(art, content, cfg, label=label))
    if check.ok:
        return Outcome(content, "verified", version, checks=[check])
    log.info("vérification %s: échec, correction demandée", art.paper.arxiv_id)
    req, version = gen_req(art, cfg, feedback=check.feedback, label=label)
    content = llm.run(req)
    check2 = llm.run(verify_req(art, content, cfg, label=label))
    return Outcome(content, "verified" if check2.ok else "unverified", version, True, [check, check2])


def generate_verified_batch(llm: LLM, arts: list[Article], cfg: Config) -> dict[str, Outcome]:
    """Mode Batches : quatre lots au plus (génération, vérification, corrections, re-vérification).

    Renvoie les articles aboutis, par identifiant arXiv ; ceux dont la génération a échoué manquent.
    """
    out: dict[str, Outcome] = {}

    def gen_round(pending: list[Article], feedback: dict[str, str]) -> dict[str, tuple[GeneratedContent, str]]:
        built = [gen_req(a, cfg, batch=True, feedback=feedback.get(a.paper.arxiv_id, "")) for a in pending]
        results = llm.run_batch([r for r, _ in built])
        done = {}
        for a, (_, version), res in zip(pending, built, results):
            if isinstance(res, Exception):
                log.warning("génération %s: %r", a.paper.arxiv_id, res)
            else:
                done[a.paper.arxiv_id] = (res, version)
        return done

    def verify_round(pending: list[Article], contents: dict[str, tuple[GeneratedContent, str]]) -> dict[str, Verification]:
        todo = [a for a in pending if a.paper.arxiv_id in contents]
        results = llm.run_batch([verify_req(a, contents[a.paper.arxiv_id][0], cfg, batch=True) for a in todo])
        checks = {}
        for a, res in zip(todo, results):
            if isinstance(res, Exception):
                log.warning("vérification %s: %r", a.paper.arxiv_id, res)
            else:
                checks[a.paper.arxiv_id] = res
        return checks

    contents = gen_round(arts, {})
    checks = verify_round(arts, contents)
    retry: list[Article] = []
    for a in arts:
        aid = a.paper.arxiv_id
        if aid not in contents:
            continue
        content, version = contents[aid]
        check = checks.get(aid)
        if check is None:  # vérification en erreur : le contenu existe mais n'est pas vérifié
            out[aid] = Outcome(content, "unverified", version)
        elif check.ok:
            out[aid] = Outcome(content, "verified", version, checks=[check])
        else:
            out[aid] = Outcome(content, "unverified", version, checks=[check])
            retry.append(a)

    if retry:
        log.info("corrections demandées pour %d articles", len(retry))
        contents2 = gen_round(retry, {a.paper.arxiv_id: checks[a.paper.arxiv_id].feedback for a in retry})
        checks2 = verify_round(retry, contents2)
        for a in retry:
            aid = a.paper.arxiv_id
            if aid not in contents2:
                continue  # on garde la première version, marquée non vérifiée
            content, version = contents2[aid]
            check2 = checks2.get(aid)
            first = out[aid].checks
            out[aid] = Outcome(
                content,
                "verified" if check2 is not None and check2.ok else "unverified",
                version,
                True,
                first + ([check2] if check2 else []),
            )
    return out
