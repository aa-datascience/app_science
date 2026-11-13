"""Étapes 3, 5 et 6 — classement, génération, vérification."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

from .config import REPO_ROOT, Config
from .llm import LLM
from .models import Candidate, GeneratedContent, Paper, RankBatch, Ranked, Verification

log = logging.getLogger(__name__)
PROMPTS = REPO_ROOT / "prompts"


def load_prompt(name: str, prompts_dir: Path = PROMPTS) -> tuple[str, str]:
    """Renvoie (texte, version) ; la version est l'empreinte du fichier."""
    text = (prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()[:10]


def render(template: str, **values: str) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template.strip()


def _source_note(source: str, truncated: bool) -> str:
    note = {
        "html": "full text",
        "latex": "full LaTeX source",
        "pdf": "text extracted from the PDF; equations may be garbled",
        "abstract": "ABSTRACT ONLY, the full text was not available",
    }[source]
    return note + ("; the text was cut at a length limit and its end is missing" if truncated else "")


def _article_block(text: str) -> dict:
    # Le texte de l'article est le préfixe commun à la génération, à la vérification
    # et à leurs relances : on le met en cache.
    return {"type": "text", "text": f"<paper>\n{text}\n</paper>", "cache_control": {"type": "ephemeral"}}


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
        out = llm.parse(step="rank", model=cfg.models.rank, system=system, content=prompt, schema=RankBatch)
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


def generate(
    llm: LLM,
    paper: Paper,
    text: str,
    source: str,
    truncated: bool,
    cfg: Config,
    feedback: str = "",
) -> tuple[GeneratedContent, str]:
    """Renvoie (contenu, version du prompt). `feedback` : corrections du vérificateur."""
    system, _ = load_prompt("system")
    template, version = load_prompt("generate")
    level = cfg.profile.levels.get(paper.primary_category, "intermediate")
    fb = (
        "A reviewer checked your previous entry against the paper and found problems. "
        "Write the entry again with these corrected, removing anything the paper does not support:\n" + feedback
        if feedback
        else ""
    )
    prompt = render(
        template,
        source_note=_source_note(source, truncated),
        title=paper.title,
        authors=", ".join(paper.authors[:12]) + (" et al." if len(paper.authors) > 12 else ""),
        arxiv_id=paper.arxiv_id,
        categories=", ".join(paper.categories),
        level=level,
        feedback=fb,
    )
    content = llm.parse(
        step="generate",
        model=cfg.models.generate,
        system=system,
        content=[_article_block(text), {"type": "text", "text": prompt}],
        schema=GeneratedContent,
    )
    return content, version


# ---------- Étape 6 : vérification ----------


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def missing_quotes(content: GeneratedContent, text: str) -> list[str]:
    """Citations des claims introuvables telles quelles dans le texte (contrôle sans IA)."""
    hay = _norm(text)
    return [c.quote for c in content.claims if _norm(c.quote) not in hay]


def verify(
    llm: LLM, content: GeneratedContent, text: str, source: str, truncated: bool, cfg: Config
) -> Verification:
    system, _ = load_prompt("system")
    template, _ = load_prompt("verify")
    missing = missing_quotes(content, text)
    quote_check = (
        "An exact string search did not find these supporting quotes in the paper. "
        "They may be paraphrased, differ only in formatting, or be invented; check each one:\n"
        + "\n".join(f"- {q}" for q in missing)
        if missing
        else ""
    )
    prompt = render(
        template,
        source_note=_source_note(source, truncated),
        quote_check=quote_check,
        entry=content.model_dump_json(indent=2),
    )
    return llm.parse(
        step="verify",
        model=cfg.models.verify,
        system=system,
        content=[_article_block(text), {"type": "text", "text": prompt}],
        schema=Verification,
    )


def generate_verified(
    llm: LLM, paper: Paper, text: str, source: str, truncated: bool, cfg: Config
) -> tuple[GeneratedContent, str, str]:
    """Génère puis vérifie ; une correction si la vérification échoue.

    Renvoie (contenu, statut "verified" | "unverified", version du prompt).
    """
    content, version = generate(llm, paper, text, source, truncated, cfg)
    check = verify(llm, content, text, source, truncated, cfg)
    if check.ok:
        return content, "verified", version
    log.info("vérification %s: échec, correction (%s)", paper.arxiv_id, check.feedback[:200])
    content, version = generate(llm, paper, text, source, truncated, cfg, feedback=check.feedback)
    check = verify(llm, content, text, source, truncated, cfg)
    return content, ("verified" if check.ok else "unverified"), version
