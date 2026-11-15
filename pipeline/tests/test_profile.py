"""Profil appris : règles d'apprentissage, signaux implicites, application à la configuration."""

import pytest
from test_store import FakeRest

from arxiv_digest.profile import apply_profile, implicit_signals, initial_rows, learn, sync_profile
from arxiv_digest.store import LocalStore

PAPER = {"title": "Josephson diode in a nanowire", "abstract": "We study supercurrent.", "categories": ["cond-mat.supr-con", "quant-ph"]}


def w(kind, key, weight, baseline=None, locked=False):
    return {"kind": kind, "key": key, "weight": weight, "baseline": weight if baseline is None else baseline, "locked": locked}


def weights():
    return [
        w("category", "cond-mat.supr-con", 1.0), w("category", "quant-ph", 1.0), w("category", "hep-th", 1.5, 1.0),
        w("keyword", "josephson", 1.0), w("keyword", "vortex", 0.5), w("keyword", "benchmark", -0.5),
    ]


def run(signals, editions=0, ws=None, levels=None):
    cw, cl, ch = learn(ws or weights(), levels or [], signals, editions=editions, day="2026-11-14")
    return {(x["kind"], x["key"]): x["weight"] for x in cw}, cl, ch


def test_explicit_feedback_moves_primary_fully_secondary_by_half_and_matching_keywords():
    got, _, changes = run([{"type": "interesting", "paper": PAPER}, {"type": "saved", "paper": PAPER}])
    assert got == {
        ("category", "cond-mat.supr-con"): pytest.approx(1.15), ("category", "quant-ph"): pytest.approx(1.075),
        ("keyword", "josephson"): pytest.approx(1.15),
    }  # « vortex » absent de l'article, hep-th non concerné, mot-clé négatif jamais appris
    reasons = {c["key"]: c["reason"] for c in changes}
    assert reasons["josephson"] == "1 interesting, 1 saved"
    assert all(c["source"] == "feedback" for c in changes)


def test_implicit_signals_are_weak():
    got, _, _ = run([{"type": "read", "paper": PAPER}])
    assert got[("category", "cond-mat.supr-con")] == pytest.approx(1.025)
    got, _, _ = run([{"type": "ignored", "paper": PAPER}])
    assert got[("category", "cond-mat.supr-con")] == pytest.approx(0.9875)
    assert got[("category", "quant-ph")] == pytest.approx(0.9938, abs=1e-4)


def test_decay_goes_to_baseline_once_per_edition_and_is_not_logged():
    got, _, changes = run([], editions=2)
    assert got == {("category", "hep-th"): pytest.approx(1.5 - 0.5 * (1 - 0.98**2), abs=1e-4)}
    assert changes == []
    assert run([], editions=0)[0] == {}


def test_bounds_and_lock():
    ws = [w("category", "cond-mat.supr-con", 1.98), w("category", "quant-ph", 1.0, locked=True), w("keyword", "josephson", 0.22)]
    got, _, _ = run([{"type": "saved", "paper": PAPER}], ws=ws)
    assert got == {("category", "cond-mat.supr-con"): 2.0, ("keyword", "josephson"): pytest.approx(0.32)}
    got, _, _ = run([{"type": "not_interesting", "paper": PAPER}], ws=[w("keyword", "josephson", 0.22)])
    assert got == {("keyword", "josephson"): 0.2}


def test_level_changes_after_three_more_too_easy_than_too_hard():
    easy, hard = {"type": "too_easy", "paper": PAPER}, {"type": "too_hard", "paper": PAPER}
    _, levels, changes = run([easy, easy, hard])
    assert levels == [{"category": "cond-mat.supr-con", "level": "intermediate", "drift": 1, "locked": False}] and changes == []
    _, levels, changes = run([easy, easy], levels=levels)
    assert (levels[0]["level"], levels[0]["drift"]) == ("expert", 0)
    assert changes[0]["kind"] == "level" and (changes[0]["old_value"], changes[0]["new_value"]) == ("intermediate", "expert")
    _, levels, changes = run([easy, easy, easy, easy], levels=levels)  # déjà au maximum
    assert (levels[0]["level"], levels[0]["drift"]) == ("expert", 3) and changes == []
    locked = [{"category": "cond-mat.supr-con", "level": "beginner", "drift": 0, "locked": True}]
    assert run([easy, easy, easy], levels=locked)[1] == []


def test_implicit_signals_need_two_seconds_and_no_explicit_feedback():
    items = [{"edition_date": "2026-11-13", "paper_id": f"p{i}", "papers": PAPER} for i in range(5)]
    events = [
        {"edition_date": "2026-11-13", "paper_id": "p0", "event": "opened", "duration_ms": None},
        {"edition_date": "2026-11-13", "paper_id": "p0", "event": "viewed", "duration_ms": 9000},
        {"edition_date": "2026-11-13", "paper_id": "p1", "event": "viewed", "duration_ms": 1200},
        {"edition_date": "2026-11-13", "paper_id": "p1", "event": "viewed", "duration_ms": 900},   # 2,1 s au total
        {"edition_date": "2026-11-13", "paper_id": "p2", "event": "viewed", "duration_ms": 1999},  # passée trop vite
        {"edition_date": "2026-11-13", "paper_id": "p3", "event": "opened", "duration_ms": None},  # avis explicite
        {"edition_date": "2026-11-12", "paper_id": "p4", "event": "opened", "duration_ms": None},  # autre édition
    ]
    got = implicit_signals(items, events, {"p3"})
    assert [s["type"] for s in got] == ["read", "ignored"]


def test_initial_rows_and_apply_roundtrip(cfg):
    ws, levels = initial_rows(cfg)
    assert {x["kind"] for x in ws} == {"category", "keyword"}
    assert all(x["weight"] < 0 for x in ws if x["key"] in cfg.prefilter.keywords_negative)
    out = apply_profile(cfg, ws, levels, {})
    assert out.categories.followed == cfg.categories.followed
    assert out.prefilter.keywords_positive == cfg.prefilter.keywords_positive
    assert out.prefilter.keywords_negative == cfg.prefilter.keywords_negative


def test_apply_profile_uses_database_values(cfg):
    explo = cfg.categories.exploration[0]
    ws = [w("category", "quant-ph", 1.3), w("category", explo, 1.0), w("keyword", "josephson", 1.7), w("keyword", "survey", -0.5)]
    levels = [{"category": "quant-ph", "level": "expert", "drift": 0, "locked": False}]
    out = apply_profile(cfg, ws, levels, {"edition_size": 40})
    assert out.categories.followed == {"quant-ph": 1.3, explo: 1.0}
    assert explo not in out.categories.exploration  # une catégorie suivie n'est plus de l'exploration
    assert out.prefilter.keywords_positive == {"josephson": 1.7} and out.prefilter.keywords_negative == {"survey": 0.5}
    assert out.profile.levels["quant-ph"] == "expert" and out.edition.size == 12
    assert apply_profile(cfg, [], [], {"edition_size": "x"}).edition.size == cfg.edition.size
    assert cfg.edition.size != 12  # la configuration d'origine n'est pas modifiée


def test_sync_without_database_is_a_no_op(cfg, tmp_path):
    assert sync_profile(LocalStore(tmp_path), cfg, "2026-11-14") is cfg


def test_sync_seeds_then_learns_and_moves_cursors(cfg, tmp_path):
    rest = FakeRest({
        "profile": [{"settings": {"edition_size": 6}, "learned_feedback_id": 4, "learned_through": "2026-11-12"}],
        "feedback": [{"id": 7, "type": "interesting", "paper_id": "a", "papers": PAPER}],
        "editions": [{"date": "2026-11-14"}, {"date": "2026-11-13"}],
        "edition_items": [{"edition_date": "2026-11-13", "paper_id": "b", "papers": PAPER}],
        "reading_events": [{"edition_date": "2026-11-13", "paper_id": "b", "event": "opened", "duration_ms": None}],
    })
    out = sync_profile(rest.store(tmp_path), cfg, "2026-11-14")
    assert out.edition.size == 6
    writes = [r for r in rest.requests if r["method"] != "GET"]
    assert [(r["method"], r["table"]) for r in writes] == [
        ("POST", "profile_weights"),  # initialisation depuis config.yaml
        ("POST", "profile_weights"), ("POST", "profile_changes"), ("PATCH", "profile"),
    ]
    assert len(writes[0]["body"]) == len(initial_rows(cfg)[0])
    # FakeRest ne filtre pas : l'édition du 14 revient aussi, d'où deux éditions traitées.
    assert writes[-1]["body"] == {"learned_feedback_id": 7, "learned_through": "2026-11-14"}
    fb = next(r for r in rest.requests if r["table"] == "feedback" and "id" in r["params"])
    assert fb["params"]["id"] == "gt.4"
    span = next(r for r in rest.requests if r["table"] == "edition_items")
    assert span["params"]["and"] == "(edition_date.gt.2026-11-12,edition_date.lt.2026-11-14)"
    # La même nuit relancée : curseurs à jour, rien à apprendre ni à écrire.
    rest2 = FakeRest({
        "profile": [{"settings": {}, "learned_feedback_id": 7, "learned_through": "2026-11-14"}],
        "profile_weights": [w("category", "quant-ph", 1.0)],
        "editions": [{"date": "2026-11-14"}],
    })
    sync_profile(rest2.store(tmp_path), cfg, "2026-11-14")
    assert [r["table"] for r in rest2.requests if r["method"] != "GET"] == ["profile"]
    assert "learned_through" not in rest2.requests[-1]["body"]  # la dernière édition parue n'est pas encore terminée
    assert not any(r["table"] == "edition_items" for r in rest2.requests)


def test_sync_read_only_never_writes(cfg, tmp_path):
    rest = FakeRest({"profile": [{"settings": {}}], "feedback": [{"id": 9, "type": "saved", "paper_id": "a", "papers": PAPER}]})
    sync_profile(rest.store(tmp_path), cfg, "2026-11-14", learning=False)
    assert all(r["method"] == "GET" for r in rest.requests)
