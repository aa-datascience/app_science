"""Score final et sélection de l'édition (diversité + emplacement exploration)."""

from __future__ import annotations

from .config import Config
from .models import Ranked


def final_score(r: Ranked, weights: dict[str, float], max_prefilter: float) -> float:
    norm = lambda v: (v - 1) / 4  # noqa: E731  notes 1-5 -> 0-1
    pre = r.candidate.prefilter_score / max_prefilter if max_prefilter > 0 else 0.0
    return (
        weights.get("relevance", 0) * norm(r.rank.relevance)
        + weights.get("importance", 0) * norm(r.rank.importance)
        + weights.get("novelty", 0) * norm(r.rank.novelty)
        + weights.get("prefilter", 0) * max(0.0, min(1.0, pre))
    )


def score_all(ranked: list[Ranked], cfg: Config) -> list[Ranked]:
    max_pre = max((r.candidate.prefilter_score for r in ranked), default=0.0)
    for r in ranked:
        r.final_score = round(final_score(r, cfg.scoring.weights, max_pre), 4)
    return ranked


def select_edition(ranked: list[Ranked], cfg: Config, size: int | None = None) -> list[Ranked]:
    """N meilleurs avec au plus max_per_category par catégorie principale, plus l'exploration.

    L'exploration est choisie sur importance + nouveauté (pas la pertinence : son rôle
    est justement de sortir du profil). Sans candidat exploration, on complète en principal.
    """
    size = size or cfg.edition.size
    n_explo = min(cfg.edition.exploration_slots, size)

    explo_pool = sorted(
        (r for r in ranked if r.candidate.slot == "exploration"),
        key=lambda r: (-(r.rank.importance + r.rank.novelty), r.candidate.paper.arxiv_id),
    )
    explo = explo_pool[:n_explo]

    main_pool = sorted(
        (r for r in ranked if r.candidate.slot == "main"),
        key=lambda r: (-r.final_score, r.candidate.paper.arxiv_id),
    )
    main: list[Ranked] = []
    per_cat: dict[str, int] = {}
    skipped: list[Ranked] = []
    for r in main_pool:
        if len(main) >= size - len(explo):
            break
        cat = r.candidate.paper.primary_category
        if per_cat.get(cat, 0) >= cfg.edition.max_per_category:
            skipped.append(r)
            continue
        per_cat[cat] = per_cat.get(cat, 0) + 1
        main.append(r)
    # Si la contrainte de diversité empêche de remplir l'édition, on la relâche.
    for r in skipped:
        if len(main) >= size - len(explo):
            break
        main.append(r)
    main.sort(key=lambda r: -r.final_score)
    return main + explo
