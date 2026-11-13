"""Vérification sans appel au modèle : chaque affirmation doit citer un passage présent dans l'article.

La correspondance est tolérante : casse, espaces, ponctuation et mise en forme LaTeX
sont ignorés. Ce contrôle garantit que la citation existe dans l'article ; il ne juge
pas si elle appuie réellement l'affirmation.
"""

from __future__ import annotations

import re
import unicodedata

from .models import Claim, Detail

MAX_FAILED_SHARE = 1 / 3  # au-delà, l'article est marqué « non vérifié »
MIN_QUOTE_CHARS = 20  # après normalisation ; en dessous, une citation ne prouve rien

# Commandes LaTeX de pure mise en forme : leur présence ou absence ne change pas le sens.
_FORMAT_CMD = re.compile(
    r"\\(?:mathrm|mathbf|mathit|mathcal|mathbb|mathsf|boldsymbol|bm|text|textrm|textit|textbf|emph|"
    r"operatorname|left|right|big|Big|bigg|Bigg|displaystyle|rm|it|bf|quad|qquad|,|;|!|:| )(?![a-zA-Z])"
)


def normalize(s: str) -> str:
    """Ne garde que lettres et chiffres, en minuscules : « $T_{c}$ » et « T_c » donnent « tc »."""
    s = unicodedata.normalize("NFKC", s)
    s = _FORMAT_CMD.sub("", s)
    return "".join(ch for ch in s.lower() if ch.isalnum())


def quote_found(quote: str, normalized_text: str) -> bool:
    q = normalize(quote)
    return len(q) >= MIN_QUOTE_CHARS and q in normalized_text


def check_claims(detail: Detail, text: str) -> tuple[Detail, list[Claim], str]:
    """Retire les affirmations dont la citation est introuvable.

    Renvoie (détail sans ces affirmations, affirmations retirées, statut).
    Statut « unverified » si plus d'un tiers des affirmations échouent, ou s'il n'y en a aucune.
    """
    hay = normalize(text)
    kept = [c for c in detail.claims if quote_found(c.quote, hay)]
    removed = [c for c in detail.claims if not quote_found(c.quote, hay)]
    total = len(detail.claims)
    ok = total > 0 and len(removed) <= total * MAX_FAILED_SHARE
    return detail.model_copy(update={"claims": kept}), removed, "verified" if ok else "unverified"
