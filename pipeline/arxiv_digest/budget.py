"""Plafond mensuel.

La nuit : le nombre de cartes est décidé AVANT de commencer l'édition.
À l'ouverture d'un article : le détail est refusé s'il ferait dépasser le plafond.
"""

from __future__ import annotations

import calendar
import math
from datetime import date

from .config import Config
from .llm import usage_cost

RANKING_COST_USD = 0.02  # classement d'une centaine de résumés sur le modèle rapide : marge large


def month_spent(rows: list[dict], day: str) -> float:
    return sum(r["cost_usd"] for r in rows if r["date"][:7] == day[:7])


def estimate_cost(cfg: Config, rows: list[dict], step: str, *, batch: bool = False) -> float:
    """Coût attendu d'un appel `card` ou `detail` avec le modèle configuré.

    Moyenne des 20 derniers appels du journal avec ce modèle (et ce mode de texte
    pour le détail) ; à défaut, estimation à partir des prix et de assumed_tokens.
    """
    model = cfg.models.card if step == "card" else cfg.models.generate
    costs = [
        # Ramené au prix synchrone pour pouvoir mélanger les deux modes.
        r["cost_usd"] * (2 if r.get("batch") else 1)
        for r in rows
        if r["step"] == step and r["model"] == model
        and (step == "card" or r.get("mode", "full") == cfg.fulltext.mode)
    ][-20:]
    if costs:
        sync_cost = sum(costs) / len(costs)
    else:
        tokens_in, tokens_out = cfg.budget.assumed_tokens[step]
        row = {
            "input_tokens": tokens_in,
            "cache_write_5m_tokens": 0,
            "cache_write_1h_tokens": 0,
            "cache_read_tokens": 0,
            "output_tokens": tokens_out,
        }
        sync_cost = usage_cost(cfg.budget.prices.get(model, [0.0, 0.0]), row)
    return sync_cost * (0.5 if batch else 1.0)


def affordable_size(
    size: int, *, monthly_cap: float, spent: float, day: str, per_article: float, fixed: float = RANKING_COST_USD
) -> int:
    """Nombre de cartes que le budget du jour permet.

    Le budget restant du mois est réparti sur les jours restants (aujourd'hui compris),
    pour ne pas tout dépenser en début de mois.
    """
    d = date.fromisoformat(day)
    days_left = calendar.monthrange(d.year, d.month)[1] - d.day + 1
    allowance = max(0.0, monthly_cap - spent) / days_left - fixed
    if per_article <= 0:
        return size
    return max(0, min(size, math.floor(allowance / per_article + 1e-9)))


def can_open(*, monthly_cap: float, spent: float, estimate: float) -> bool:
    """Vrai si le détail d'un article tient encore dans le plafond mensuel."""
    return spent + estimate <= monthly_cap
