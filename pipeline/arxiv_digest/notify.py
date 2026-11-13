"""Notifications : une le matin (édition prête), un rappel le soir si elle n'est pas terminée. Rien d'autre.

Lancé par GitHub Actions à heures fixes (voir .github/workflows/notify.yml). La commande décide
elle-même si la notification est due : heure locale atteinte, pas déjà envoyée aujourd'hui.
Envoi par le service de push d'Expo, vers le jeton que l'app enregistre dans profile.push_token.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from .store import SupabaseStore, make_store

log = logging.getLogger(__name__)
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
DEFAULTS = {"timezone": "Europe/Zurich", "morning_time": "07:30", "evening_time": "20:00"}


def decide(kind: str, now: datetime, edition: dict | None, settings: dict) -> str | None:
    """Le texte de la notification à envoyer maintenant, ou None s'il n'y a rien à envoyer.

    `now` est l'heure locale de l'utilisateur ; `edition` vient de SupabaseStore.edition_state.
    """
    if edition is None or edition["status"] not in ("ready", "fallback") or not edition["n_items"]:
        return None  # pas d'édition prête : on ne notifie jamais pour rien
    if edition.get(f"{kind}_notified_at"):
        return None  # déjà envoyée aujourd'hui
    due = settings.get(f"{kind}_time") or DEFAULTS[f"{kind}_time"]
    if now.strftime("%H:%M") < due:
        return None
    n = edition["n_items"]
    if kind == "morning":
        return f"Today's edition is ready — {n} paper{'s' if n > 1 else ''}"
    # Soir : seulement si l'édition n'est pas terminée. Une édition terminée coupe toute notification.
    remaining = n - edition["n_shown"]
    if edition.get("completed_at") or remaining <= 0:
        return None
    return f"{remaining} paper{'s' if remaining > 1 else ''} left in today's edition"


def send_push(token: str, body: str, http: httpx.Client | None = None) -> None:
    """Envoie une notification par Expo ; lève une erreur si Expo la refuse."""
    payload = {"to": token, "title": "arXiv digest", "body": body}
    r = (http or httpx).post(EXPO_PUSH_URL, json=payload, timeout=30)
    r.raise_for_status()
    data = r.json().get("data", {})
    if data.get("status") != "ok":
        raise RuntimeError(f"Expo a refusé la notification : {data.get('message') or data}")


def notify(*, out: Path, kind: str, dry_run: bool = False, now: datetime | None = None) -> int:
    store = make_store(out)
    if not isinstance(store, SupabaseStore):
        log.error("les notifications demandent Supabase (SUPABASE_URL et SUPABASE_SERVICE_KEY)")
        return 2
    profile = store.profile()
    settings = profile.get("settings") or {}
    now = now or datetime.now(ZoneInfo(settings.get("timezone") or DEFAULTS["timezone"]))
    day = now.date().isoformat()

    message = decide(kind, now, store.edition_state(day), settings)
    if message is None:
        print(f"Notification {kind} du {day} : rien à envoyer.")
        return 0
    if dry_run:
        print(f"Notification {kind} du {day} (non envoyée, --dry-run) : {message}")
        return 0
    token = profile.get("push_token")
    if not token:
        print(f"Notification {kind} due ({message}) mais aucun jeton de push : l'app ne s'est pas encore enregistrée.")
        return 0
    try:
        send_push(token, message)
    except (httpx.HTTPError, RuntimeError) as e:
        log.error("envoi impossible: %s", e)
        return 1
    store.mark_notified(day, kind)
    print(f"Notification {kind} du {day} envoyée : {message}")
    return 0
