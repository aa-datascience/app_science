"""Plafond mensuel : on décide du nombre d'articles AVANT de commencer l'édition."""

from __future__ import annotations

import calendar
import math
from datetime import date

from .config import Config
from .llm import usage_cost

RANKING_COST_USD = 0.02  # classement d'une centaine de résumés sur le modèle rapide : marge large


def month_spent(rows: list[dict], day: str) -> float:
    return sum(r["cost_usd"] for r in rows if r["date"][:7] == day[:7])


def estimate_cost_per_article(cfg: Config, rows: list[dict], *, batch: bool) -> float:
    """Coût attendu de génération + vérification d'un article.

    Moyenne des 20 derniers articles traités avec les modèles et le mode de texte
    actuels ; à défaut, estimation à partir des prix et de assumed_tokens_per_article.
    """
    per_article: dict[tuple, float] = {}
    for r in rows:
        wanted = {"generate": cfg.models.generate, "verify": cfg.models.verify}.get(r["step"])
        if r["model"] != wanted or r.get("mode", "full") != cfg.fulltext.mode or "arxiv_id" not in r:
            continue
        key = (r["date"], r["arxiv_id"], r.get("label", ""))
        # Ramené au prix synchrone pour pouvoir mélanger les deux modes.
        per_article[key] = per_article.get(key, 0.0) + r["cost_usd"] * (2 if r.get("batch") else 1)
    if per_article:
        recent = list(per_article.values())[-20:]
        sync_cost = sum(recent) / len(recent)
    else:
        tokens_in, tokens_out = cfg.budget.assumed_tokens_per_article
        prices = cfg.budget.prices.get(cfg.models.generate, [0.0, 0.0])
        sync_cost = usage_cost(
            prices,
            {
                "input_tokens": tokens_in,
                "cache_write_5m_tokens": 0,
                "cache_write_1h_tokens": 0,
                "cache_read_tokens": 0,
                "output_tokens": tokens_out,
            },
        )
    return sync_cost * (0.5 if batch else 1.0)


def affordable_size(
    size: int, *, monthly_cap: float, spent: float, day: str, per_article: float, fixed: float = RANKING_COST_USD
) -> int:
    """Nombre d'articles que le budget du jour permet.

    Le budget restant du mois est réparti sur les jours restants (aujourd'hui compris),
    pour ne pas tout dépenser en début de mois.
    """
    d = date.fromisoformat(day)
    days_left = calendar.monthrange(d.year, d.month)[1] - d.day + 1
    allowance = max(0.0, monthly_cap - spent) / days_left - fixed
    if per_article <= 0:
        return size
    return max(0, min(size, math.floor(allowance / per_article + 1e-9)))
