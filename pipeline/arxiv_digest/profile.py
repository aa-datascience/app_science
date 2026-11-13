"""Mise à jour du profil par le feedback (spec §6). Fonctions pures, branchées en V2."""

from __future__ import annotations

from typing import Literal

Feedback = Literal["interesting", "not_interesting", "saved"]

STEP = {"interesting": 0.05, "not_interesting": -0.05, "saved": 0.10}
DECAY = 0.02  # retour progressif vers la neutralité (1.0), contre l'enfermement
MIN_W, MAX_W = 0.2, 2.0


def update_category_weights(
    weights: dict[str, float], feedback: list[tuple[str, Feedback]]
) -> dict[str, float]:
    """Applique les feedbacks d'une édition puis rapproche chaque poids de 1.0.

    feedback : liste de (catégorie principale de l'article, type de feedback).
    Les catégories absentes de `weights` sont ignorées (on ne suit pas une
    catégorie par accident).
    """
    out = dict(weights)
    for cat, kind in feedback:
        if cat in out:
            out[cat] += STEP[kind]
    for cat, w in out.items():
        w += (1.0 - w) * DECAY
        out[cat] = round(max(MIN_W, min(MAX_W, w)), 4)
    return out
