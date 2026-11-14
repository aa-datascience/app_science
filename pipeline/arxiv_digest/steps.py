"""Appels au modèle : classement et cartes (la nuit), détail (à l'ouverture d'un article)."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from .citations import check_claims
from .config import REPO_ROOT, Config
from .figures import figures_for_prompt, valid_labels
from .fulltext import select_sections
from .llm import LLM, BatchFailed, LLMInvalid, LLMRefused, Req
from .models import Candidate, Card, Detail, Figure, Paper, RankBatch, Ranked, StoredDetail

log = logging.getLogger(__name__)
PROMPTS = REPO_ROOT / "prompts"


@dataclass
class Article:
    """Un article prêt pour le détail : texte récupéré, éventuellement réduit aux sections utiles."""

    paper: Paper
    text: str
    source: str  # html | latex | pdf | abstract
    truncated: bool = False
    mode: str = "full"  # full | sections (ce qui a réellement été envoyé)
    figures: list[Figure] = field(default_factory=list)
    assets: dict[str, bytes] = field(default_factory=dict)  # images de l'archive LaTeX (repli)


def make_article(
    paper: Paper,
    text: str,
    source: str,
    truncated: bool,
    mode: str,
    figures: list[Figure] | None = None,
    assets: dict[str, bytes] | None = None,
) -> Article:
    figures, assets = figures or [], assets or {}
    if mode == "sections" and source in ("html", "latex"):
        reduced, ok = select_sections(text)
        if ok:
            return Article(paper, reduced, source, truncated, "sections", figures, assets)
    return Article(paper, text, source, truncated, "full", figures, assets)


def load_prompt(name: str, prompts_dir: Path = PROMPTS) -> tuple[str, str]:
    """Renvoie (texte, version) ; la version est l'empreinte du fichier."""
    text = (prompts_dir / f"{name}.md").read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()[:10]


def render(template: str, **values: str) -> str:
    for k, v in values.items():
        template = template.replace("{{" + k + "}}", v)
    return template.strip()


def _authors(paper: Paper) -> str:
    return ", ".join(paper.authors[:12]) + (" et al." if len(paper.authors) > 12 else "")


# ---------- La nuit : classement ----------


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


# ---------- La nuit : cartes, à partir du titre et du résumé ----------


def card_req(paper: Paper, cfg: Config, label: str = "", figures: list[Figure] | None = None) -> tuple[Req, str]:
    system, _ = load_prompt("system")
    template, version = load_prompt("card")
    prompt = render(
        template,
        title=paper.title,
        authors=_authors(paper),
        arxiv_id=paper.arxiv_id,
        categories=", ".join(paper.categories),
        abstract=paper.abstract,
        figures=figures_for_prompt(figures or []),
    )
    req = Req(
        step="card",
        model=cfg.models.card,
        system=system,
        content=prompt,
        schema=Card,
        tag={"arxiv_id": paper.arxiv_id, "label": label},
        max_tokens=4000,
    )
    return req, version


def make_cards(
    llm: LLM,
    papers: list[Paper],
    cfg: Config,
    *,
    batch: bool,
    label: str = "",
    figures: dict[str, list[Figure]] | None = None,
) -> tuple[dict[str, Card], str]:
    """Une carte par article. Renvoie (cartes abouties par identifiant arXiv, version du prompt).

    batch=True : un seul lot via l'API Batches (-50 %), pour le pipeline de nuit.
    """
    figures = figures or {}
    built = [card_req(p, cfg, label, figures.get(p.arxiv_id)) for p in papers]
    version = built[0][1] if built else ""
    reqs = [r for r, _ in built]
    results = None
    if batch:
        try:
            results = llm.run_batch(reqs)
        except BatchFailed as e:  # lot trop lent ou en échec : l'édition ne doit pas en dépendre
            log.warning("cartes par lot: %s ; reprise en appels synchrones", e)
    if results is None:
        results = []
        for r in reqs:
            try:
                results.append(llm.run(r))
            except (LLMInvalid, LLMRefused, anthropic.BadRequestError) as e:
                results.append(e)  # un échec ne doit pas faire perdre les autres cartes
    cards: dict[str, Card] = {}
    for p, res in zip(papers, results):
        if isinstance(res, Exception):
            log.warning("carte %s: %r", p.arxiv_id, res)
        else:
            # Le label choisi doit exister dans la liste extraite ; sinon, pas de figure.
            res.figure = next(iter(valid_labels([res.figure], figures.get(p.arxiv_id, []), 1)), "")
            cards[p.arxiv_id] = res
    return cards, version


# ---------- À l'ouverture d'un article : détail à partir du texte complet ----------


# Ces libellés sont aussi copiés dans server_config pour l'Edge Function open-paper.
SOURCE_NOTES = {
    "html": "full text",
    "latex": "full LaTeX source",
    "pdf": "text extracted from the PDF; equations may be garbled",
    "abstract": "ABSTRACT ONLY, the full text was not available",
    "sections": "abstract, introduction, results and discussion/conclusion sections only; other sections were left out",
    "truncated": "; the text was cut at a length limit and its end is missing",
}


def _source_note(art: Article) -> str:
    note = SOURCE_NOTES["sections" if art.mode == "sections" else art.source]
    return note + (SOURCE_NOTES["truncated"] if art.truncated else "")


def detail_req(art: Article, cfg: Config, label: str = "") -> tuple[Req, str]:
    system, _ = load_prompt("system")
    template, version = load_prompt("detail")
    paper = art.paper
    prompt = render(
        template,
        source_note=_source_note(art),
        title=paper.title,
        authors=_authors(paper),
        arxiv_id=paper.arxiv_id,
        categories=", ".join(paper.categories),
        level=cfg.profile.levels.get(paper.primary_category, "intermediate"),
        figures=figures_for_prompt(art.figures),
    )
    req = Req(
        step="detail",
        model=cfg.models.generate,
        system=system,
        content=[{"type": "text", "text": f"<paper>\n{art.text}\n</paper>"}, {"type": "text", "text": prompt}],
        schema=Detail,
        tag={"arxiv_id": paper.arxiv_id, "label": label, "mode": art.mode},
    )
    return req, version


def generate_detail(llm: LLM, art: Article, cfg: Config, label: str = "") -> StoredDetail:
    """Un seul appel au modèle, puis vérification des citations sans modèle.

    Les affirmations dont la citation est introuvable dans le texte sont retirées ;
    au-delà d'un tiers d'échecs, le détail est marqué « unverified ».
    """
    req, version = detail_req(art, cfg, label)
    detail = llm.run(req)
    checked, removed, status = check_claims(detail, art.text)
    # Figures : seuls les labels présents dans la liste extraite sont gardés, trois au plus.
    kept = valid_labels([f.label for f in checked.figures], art.figures, 3)
    notes = {f.label.strip(' []'): f for f in checked.figures}
    checked = checked.model_copy(
        update={"figures": [notes[k].model_copy(update={"label": k}) for k in kept if k in notes]}
    )
    log.info(
        "détail %s: %d affirmations, %d retirées -> %s",
        art.paper.arxiv_id, len(detail.claims), len(removed), status,
    )
    return StoredDetail(
        arxiv_id=art.paper.arxiv_id,
        detail=checked,
        removed_claims=removed,
        verification_status=status,
        text_source=art.source,
        based_on_abstract=art.source == "abstract",
        text_truncated=art.truncated,
        text_mode=art.mode,
        model=cfg.models.generate,
        prompt_version=version,
    )
