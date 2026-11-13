"""Étape 2 — Présélection sans IA : mots-clés, auteurs suivis, poids par catégorie."""

from __future__ import annotations

import hashlib

from .config import Config
from .models import Candidate, Paper


def keyword_score(paper: Paper, positive: dict[str, float], negative: dict[str, float]) -> float:
    title, abstract = paper.title.lower(), paper.abstract.lower()
    score = 0.0
    for sign, table in ((1, positive), (-1, negative)):
        for kw, w in table.items():
            k = kw.lower()
            if k in title:
                score += sign * 2 * w
            elif k in abstract:
                score += sign * w
    return score


def category_score(paper: Paper, followed: dict[str, float]) -> float:
    """Poids de la meilleure catégorie suivie ; une cross-list compte pour 70 %."""
    best = 0.0
    for i, cat in enumerate(paper.categories):
        if cat in followed:
            best = max(best, followed[cat] * (1.0 if i == 0 else 0.7))
    return best


def author_score(paper: Paper, followed_authors: list[str], bonus: float) -> float:
    names = {a.lower() for a in paper.authors}
    return bonus if any(f.lower() in names for f in followed_authors) else 0.0


def prefilter_score(paper: Paper, cfg: Config) -> float:
    pf = cfg.prefilter
    return (
        category_score(paper, cfg.categories.followed)
        + keyword_score(paper, pf.keywords_positive, pf.keywords_negative)
        + author_score(paper, pf.followed_authors, pf.author_bonus)
    )


def _tiebreak(arxiv_id: str, seed: str) -> str:
    return hashlib.sha256(f"{seed}:{arxiv_id}".encode()).hexdigest()


def select_candidates(
    papers: list[Paper], cfg: Config, *, seen_ids: set[str], seed: str = ""
) -> list[Candidate]:
    """Renvoie au plus max_candidates candidats principaux + les candidats exploration.

    Un article est « exploration » s'il n'appartient à aucune catégorie suivie.
    """
    followed = cfg.categories.followed
    main: list[Candidate] = []
    explo: list[Candidate] = []
    for p in papers:
        if p.arxiv_id in seen_ids:
            continue
        score = prefilter_score(p, cfg)
        if any(c in followed for c in p.categories):
            main.append(Candidate(paper=p, prefilter_score=score, slot="main"))
        else:
            explo.append(Candidate(paper=p, prefilter_score=score, slot="exploration"))

    main.sort(key=lambda c: (-c.prefilter_score, _tiebreak(c.paper.arxiv_id, seed)))
    # Exploration : hors négatifs, ordre pseudo-aléatoire stable pour ne pas
    # reproduire les préférences du profil.
    explo = [c for c in explo if c.prefilter_score >= 0]
    explo.sort(key=lambda c: _tiebreak(c.paper.arxiv_id, seed))
    return main[: cfg.prefilter.max_candidates] + explo[: cfg.prefilter.max_exploration_candidates]
