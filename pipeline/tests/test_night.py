"""Pipeline de nuit relançable sans risque, et notifications."""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from test_llm import FakeClient, make_llm
from test_pipeline import FIXTURES, paper
from test_store import FakeRest

import arxiv_digest.notify as notify_mod
from arxiv_digest.llm import LLM, BatchFailed
from arxiv_digest.notify import decide, notify
from arxiv_digest.steps import make_cards

ZURICH = ZoneInfo("Europe/Zurich")


@pytest.fixture
def night(cfg, monkeypatch, tmp_path):
    """Lance cli.run sur les flux enregistrés (annonce du 2026-11-13), avec un client factice."""
    import arxiv_digest.cli as cli

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    client = FakeClient()
    monkeypatch.setattr(cli, "LLM", lambda c, log, day: LLM(c, log, day, client=client))

    def run(day, **kw):
        return cli.run(cfg, day=day, out=tmp_path, no_llm=False, size=3, fixtures=FIXTURES, batch=False, **kw)

    return run, client, tmp_path


def edition(tmp_path, day):
    return json.loads((tmp_path / "editions" / f"{day}.json").read_text(encoding="utf-8"))


# ---------- pipeline de nuit ----------


def test_second_run_of_the_day_does_nothing(night):
    run, client, tmp_path = night
    assert run("2026-11-13") == 0
    first, n_calls = edition(tmp_path, "2026-11-13"), len(client.calls)
    assert run("2026-11-13") == 0
    assert len(client.calls) == n_calls and edition(tmp_path, "2026-11-13") == first  # ni appel ni réécriture
    assert run("2026-11-13", force=True) == 0 and len(client.calls) > n_calls


def test_stale_feed_waits_then_falls_back_to_reserve(night):
    run, client, tmp_path = night
    assert run("2026-11-13") == 0  # remplit la réserve avec les articles non retenus
    shown = {i["paper"]["arxiv_id"] for i in edition(tmp_path, "2026-11-13")["items"]}
    n_calls = len(client.calls)

    # Le lendemain, le flux contient encore l'annonce du 13 : le premier lancement attend.
    assert run("2026-11-14", stale="wait") == 0
    assert len(client.calls) == n_calls and not (tmp_path / "editions" / "2026-11-14.json").exists()

    # Le dernier lancement de la nuit puise dans la réserve, sans reclasser ni remontrer un article.
    assert run("2026-11-14", stale="reserve") == 0
    e = edition(tmp_path, "2026-11-14")
    assert e["status"] == "ready" and len(e["items"]) == 3 and "réserve" in e["notes"][0]
    assert not shown & {i["paper"]["arxiv_id"] for i in e["items"]}
    props = [c["output_config"]["format"]["schema"]["properties"] for c in client.calls[n_calls:]]
    assert all("plain_title" in p for p in props)  # des cartes seulement, aucun classement


def test_cards_fall_back_to_sync_calls_when_batch_fails(cfg, tmp_path):
    class FailingBatches(FakeClient):
        def create(self, **kwargs):
            if "requests" in kwargs:
                raise BatchFailed("lot annulé")
            return super().create(**kwargs)

    client = FailingBatches()
    cards, _ = make_cards(make_llm(cfg, tmp_path, client), [paper(1), paper(2)], cfg, batch=True)
    assert len(cards) == 2 and len(client.calls) == 2


# ---------- notifications ----------


def state(**kw):
    return {"status": "ready", "n_items": 8, "n_shown": 3, "completed_at": None,
            "morning_notified_at": None, "evening_notified_at": None, **kw}


def at(hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime(2026, 11, 13, h, m, tzinfo=ZURICH)


def test_morning_notification_only_when_ready_due_and_not_sent():
    assert decide("morning", at("07:35"), state(), {}) == "Today's edition is ready — 8 papers"
    assert decide("morning", at("07:35"), state(n_items=1), {}) == "Today's edition is ready — 1 paper"
    assert decide("morning", at("06:35"), state(), {}) is None  # trop tôt
    assert decide("morning", at("06:35"), state(), {"morning_time": "06:30"}) is not None  # heure réglable
    assert decide("morning", at("07:35"), state(morning_notified_at="x"), {}) is None  # déjà envoyée
    assert decide("morning", at("07:35"), state(status="failed"), {}) is None
    assert decide("morning", at("07:35"), state(status="pending"), {}) is None
    assert decide("morning", at("07:35"), None, {}) is None  # pas d'édition : pas de notification


def test_evening_reminder_only_if_edition_unfinished():
    assert decide("evening", at("20:05"), state(), {}) == "5 papers left in today's edition"
    assert decide("evening", at("20:05"), state(n_shown=7), {}) == "1 paper left in today's edition"
    assert decide("evening", at("19:05"), state(), {}) is None  # trop tôt
    assert decide("evening", at("20:05"), state(completed_at="x"), {}) is None  # terminée : plus rien
    assert decide("evening", at("20:05"), state(n_shown=8), {}) is None
    assert decide("evening", at("20:05"), state(evening_notified_at="x"), {}) is None


def notify_with(monkeypatch, tmp_path, tables, expo_status="ok"):
    rest = FakeRest(tables)
    monkeypatch.setattr(notify_mod, "make_store", lambda out: rest.store(tmp_path))
    sent = []

    def fake_post(url, json, timeout):
        sent.append((url, json))
        return httpx.Response(200, json={"data": {"status": expo_status, "message": "DeviceNotRegistered"}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(notify_mod.httpx, "post", fake_post)
    return rest, sent


TABLES = {
    "editions": [{"date": "2026-11-13", "status": "ready", "completed_at": None,
                  "morning_notified_at": None, "evening_notified_at": None}],
    "edition_items": [{"paper_id": "a"}, {"paper_id": "b"}, {"paper_id": "c"}],
    "reading_events": [{"paper_id": "a"}, {"paper_id": "a"}, {"paper_id": "zzz"}],
    "profile": [{"settings": {}, "push_token": "ExponentPushToken[x]"}],
}


def test_notify_sends_once_and_marks_the_edition(monkeypatch, tmp_path):
    rest, sent = notify_with(monkeypatch, tmp_path, TABLES)
    assert notify(out=tmp_path, kind="evening", now=at("20:05")) == 0
    assert sent == [(notify_mod.EXPO_PUSH_URL, {"to": "ExponentPushToken[x]", "title": "arXiv digest",
                                               "body": "2 papers left in today's edition"})]
    patch = rest.requests[-1]
    assert patch["method"] == "PATCH" and patch["params"] == {"date": "eq.2026-11-13"}
    assert list(patch["body"]) == ["evening_notified_at"]


def test_notify_does_not_mark_when_nothing_is_sent(monkeypatch, tmp_path):
    def writes(rest):
        return [r for r in rest.requests if r["method"] != "GET"]

    rest, sent = notify_with(monkeypatch, tmp_path, TABLES)
    assert notify(out=tmp_path, kind="morning", now=at("06:00")) == 0  # trop tôt
    assert notify(out=tmp_path, kind="morning", now=at("07:35"), dry_run=True) == 0
    assert sent == [] and writes(rest) == []

    no_token = {**TABLES, "profile": [{"settings": {}, "push_token": None}]}
    rest, sent = notify_with(monkeypatch, tmp_path, no_token)
    assert notify(out=tmp_path, kind="morning", now=at("07:35")) == 0  # l'app n'est pas encore installée
    assert sent == [] and writes(rest) == []

    rest, sent = notify_with(monkeypatch, tmp_path, TABLES, expo_status="error")
    assert notify(out=tmp_path, kind="morning", now=at("07:35")) == 1  # refus d'Expo : sera retentée
    assert len(sent) == 1 and writes(rest) == []
