"""Appels au modèle, lots, plafond mensuel, sections, bout en bout — avec un client factice."""

import json
from types import SimpleNamespace

import pytest
from test_pipeline import FIXTURES, content_with, paper

from arxiv_digest.budget import affordable_size, estimate_cost_per_article, month_spent
from arxiv_digest.fulltext import select_sections
from arxiv_digest.llm import LLM, BudgetExceeded, read_usage, usage_cost
from arxiv_digest.models import Candidate, RankBatch, RankItem, Verification
from arxiv_digest.steps import Article, generate_verified, generate_verified_batch, make_article, rank


class FakeClient:
    """Client factice : répond selon le schéma demandé. Sert aussi de faux service Batches."""

    def __init__(self, verify_ok=(True,)):
        self.calls, self.verify_ok = [], list(verify_ok)
        self.messages = self
        self.batches = self
        self.batch_requests = []

    def _answer(self, params):
        props = params["output_config"]["format"]["schema"]["properties"]
        if "items" in props:
            text = params["messages"][0]["content"]
            ids = [line.split()[1] for line in text.splitlines() if line.startswith("arxiv_id:")]
            out = RankBatch(
                items=[RankItem(arxiv_id=i, relevance=4, importance=3, novelty=3, difficulty=2, why="w") for i in ids]
            )
        elif "card" in props:
            out = content_with(["a quote"])
        else:
            ok = self.verify_ok.pop(0) if len(self.verify_ok) > 1 else self.verify_ok[0]
            out = Verification(verdicts=[], unsupported_numbers=[], ok=ok, feedback="" if ok else "fix it")
        usage = SimpleNamespace(
            input_tokens=1000, output_tokens=100, cache_creation_input_tokens=0, cache_read_input_tokens=0
        )
        block = SimpleNamespace(type="text", text=out.model_dump_json())
        return SimpleNamespace(content=[block], stop_reason="end_turn", usage=usage)

    def create(self, **kwargs):
        if "requests" in kwargs:  # batches.create
            self.batch_requests.append(kwargs["requests"])
            return SimpleNamespace(id=f"b{len(self.batch_requests)}", processing_status="ended")
        self.calls.append(kwargs)
        return self._answer(kwargs)

    def results(self, batch_id):
        reqs = self.batch_requests[int(batch_id[1:]) - 1]
        for r in reversed(reqs):  # ordre quelconque, comme la vraie API
            result = SimpleNamespace(type="succeeded", message=self._answer(r["params"]))
            yield SimpleNamespace(custom_id=r["custom_id"], result=result)


def make_llm(cfg, tmp_path, client, **kw):
    return LLM(cfg, tmp_path / "usage.jsonl", "2026-11-13", client=client, **kw)


def art(i, text="Some paper text with a quote inside."):
    return Article(paper(i), text, "html")


# ---------- appels et coûts ----------


def test_rank_maps_results_and_logs_cost(cfg, tmp_path):
    cands = [
        Candidate(paper=paper(1), prefilter_score=1.0),
        Candidate(paper=paper(2), prefilter_score=0.5, slot="exploration"),
    ]
    client = FakeClient()
    llm = make_llm(cfg, tmp_path, client)
    out = rank(llm, cands, cfg)
    assert [r.candidate.paper.arxiv_id for r in out] == ["2611.00001", "2611.00002"]
    assert "2611.00002 [exploration]" in client.calls[0]["messages"][0]["content"]
    p_in, p_out = cfg.budget.prices[cfg.models.rank][:2]
    assert llm.run_spent == pytest.approx((1000 * p_in + 100 * p_out) / 1e6)
    assert month_spent(read_usage(tmp_path / "usage.jsonl"), "2026-11-30") == pytest.approx(llm.run_spent)
    assert month_spent(read_usage(tmp_path / "usage.jsonl"), "2026-12-01") == 0


def test_usage_cost_cache_and_batch_multipliers():
    row = {
        "input_tokens": 1e6,
        "cache_write_5m_tokens": 1e6,
        "cache_write_1h_tokens": 1e6,
        "cache_read_tokens": 1e6,
        "output_tokens": 1e6,
    }
    assert usage_cost([4.0, 20.0, 0.2], row) == pytest.approx(4 + 5 + 8 + 0.2 + 20)
    assert usage_cost([4.0, 20.0], {**row, "batch": True}) == pytest.approx((4 + 5 + 8 + 0.4 + 20) / 2)


def test_hard_cap_blocks_calls(cfg, tmp_path):
    llm = make_llm(cfg, tmp_path, FakeClient(), hard_cap_usd=0.0)
    with pytest.raises(BudgetExceeded):
        generate_verified(llm, art(1), cfg)


def test_sync_generation_caches_article_and_corrects_once(cfg, tmp_path):
    client = FakeClient(verify_ok=[False, True])
    o = generate_verified(make_llm(cfg, tmp_path, client), art(1), cfg, label="x")
    assert (o.status, o.corrected, len(o.checks)) == ("verified", True, 2)
    assert len(client.calls) == 4  # génération, vérification, correction, re-vérification
    blocks = [c["messages"][0]["content"][0] for c in client.calls]
    assert all(b["cache_control"] == {"type": "ephemeral"} for b in blocks)
    assert len({b["text"] for b in blocks}) == 1  # préfixe identique : le cache peut servir
    assert len({c["system"] for c in client.calls}) == 1
    assert "fix it" in client.calls[2]["messages"][0]["content"][1]["text"]
    rows = read_usage(tmp_path / "usage.jsonl")
    assert {r["label"] for r in rows} == {"x"} and rows[0]["arxiv_id"] == "2611.00001"


def test_unverified_after_two_failures(cfg, tmp_path):
    o = generate_verified(make_llm(cfg, tmp_path, FakeClient(verify_ok=[False])), art(1), cfg)
    assert o.status == "unverified" and o.corrected


def test_batch_mode_uses_batches_api_at_half_price_without_cache(cfg, tmp_path):
    # Les résultats d'un lot reviennent en ordre inverse : l'article 2 est vérifié en premier.
    client = FakeClient(verify_ok=[True, False, True])
    llm = make_llm(cfg, tmp_path, client)
    res = generate_verified_batch(llm, [art(1), art(2)], cfg)
    assert client.calls == []  # aucun appel synchrone
    assert [len(b) for b in client.batch_requests] == [2, 2, 1, 1]  # un seul article à corriger
    assert {k: (o.status, o.corrected) for k, o in res.items()} == {
        "2611.00002": ("verified", False),
        "2611.00001": ("verified", True),
    }
    assert "cache_control" not in client.batch_requests[0][0]["params"]["messages"][0]["content"][0]
    rows = read_usage(tmp_path / "usage.jsonl")
    p_in, p_out = cfg.budget.prices[cfg.models.generate][:2]
    assert all(r["batch"] for r in rows)
    assert rows[0]["cost_usd"] == pytest.approx((1000 * p_in + 100 * p_out) / 1e6 / 2)


# ---------- plafond mensuel ----------


def test_affordable_size_spreads_budget_over_remaining_days():
    kw = dict(monthly_cap=15.0, per_article=0.10, fixed=0.0)
    assert affordable_size(8, spent=0.0, day="2026-11-01", **kw) == 5  # 15 $ / 30 jours = 0,50 $ par jour
    assert affordable_size(8, spent=0.0, day="2026-11-30", **kw) == 8  # dernier jour : tout le reste
    assert affordable_size(8, spent=14.95, day="2026-11-13", **kw) == 0
    assert affordable_size(8, spent=20.0, day="2026-11-13", **kw) == 0


def test_estimate_cost_uses_history_else_prices(cfg):
    cfg.models.generate = cfg.models.verify = "claude-opus-5-5"
    t_in, t_out = cfg.budget.assumed_tokens_per_article
    assert estimate_cost_per_article(cfg, [], batch=False) == pytest.approx((t_in * 4 + t_out * 20) / 1e6)
    opus = {"date": "2026-11-12", "model": "claude-opus-5-5"}
    rows = [
        {**opus, "step": "generate", "arxiv_id": "a", "cost_usd": 0.2},
        {**opus, "step": "verify", "arxiv_id": "a", "cost_usd": 0.1},
        {**opus, "step": "generate", "arxiv_id": "b", "cost_usd": 0.05, "batch": True},
        {**opus, "step": "generate", "arxiv_id": "c", "cost_usd": 9.0, "mode": "sections"},
        {"date": "2026-11-12", "step": "generate", "model": "claude-haiku-5-5", "arxiv_id": "d", "cost_usd": 9.0},
        {"date": "2026-11-12", "step": "rank", "model": "claude-haiku-5-5", "cost_usd": 9.0},
    ]
    assert estimate_cost_per_article(cfg, rows, batch=False) == pytest.approx((0.3 + 0.1) / 2)
    assert estimate_cost_per_article(cfg, rows, batch=True) == pytest.approx(0.1)


# ---------- sections utiles ----------

SECTIONED = (
    "Title\n\nAbstract here\n\n## I Introduction\n\nintro\n\n## II Model\n\nmodel\n\n"
    "## III Results\n\nres\n\n## IV Conclusions\n\nend\n\n## Appendix A\n\napp"
)


def test_select_sections_keeps_named_sections_or_falls_back():
    out, reduced = select_sections(SECTIONED)
    assert reduced and all(x in out for x in ("Abstract here", "intro", "res", "end"))
    assert "model" not in out and "app" not in out
    by_topic = "Title\n\n## Model\n\nm\n\n## Phase diagram\n\np\n\n## Summary\n\ns"
    assert select_sections(by_topic) == (by_topic, False)  # sections par sujet, rien d'annexe : texte complet
    out, reduced = select_sections(by_topic + "\n\n## Appendix A\n\napp")
    assert reduced and "Phase diagram" in out and "app" not in out  # seules les annexes sont retirées
    assert make_article(paper(1), SECTIONED, "pdf", False, "sections").mode == "full"
    assert make_article(paper(1), SECTIONED, "html", False, "sections").mode == "sections"
    assert make_article(paper(1), SECTIONED, "html", False, "full").text == SECTIONED


# ---------- bout en bout, sans réseau ni API ----------


def test_run_end_to_end_reduces_edition_to_monthly_budget(cfg, tmp_path, monkeypatch):
    import arxiv_digest.cli as cli

    client = FakeClient()
    monkeypatch.setattr(cli, "fetch_fulltext", lambda p, **kw: ("Full text with a quote inside. " * 200, "html", False))
    monkeypatch.setattr(cli, "LLM", lambda c, path, day: LLM(c, path, day, client=client))
    cfg.budget.monthly_usd = 0.9  # 18 jours restants -> 0,05 $ par jour
    cfg.budget.prices[cfg.models.generate] = [0.1, 0.5]
    cfg.budget.assumed_tokens_per_article = (100_000, 10_000)  # 0,015 $ par article
    for batch, expected in ((False, 2), (True, 4)):  # (0,05 - 0,02) / 0,015 ; moitié prix en lots
        out = tmp_path / str(batch)
        code = cli.run(cfg, day="2026-11-13", out=out, no_llm=False, size=6, fixtures=FIXTURES, batch=batch)
        edition = json.loads((out / "editions" / "2026-11-13.json").read_text(encoding="utf-8"))
        assert code == 0 and edition["status"] == "ready"
        assert len(edition["items"]) == expected
        assert f"édition réduite de 6 à {expected}" in edition["notes"][0]
        assert all(i["verification_status"] == "verified" for i in edition["items"])
        assert len(json.loads((out / "seen.json").read_text())) == expected


def test_run_makes_no_paid_call_when_budget_is_exhausted(cfg, tmp_path, monkeypatch):
    import arxiv_digest.cli as cli

    client = FakeClient()
    monkeypatch.setattr(cli, "LLM", lambda c, path, day: LLM(c, path, day, client=client))
    cfg.budget.monthly_usd = 0.0
    code = cli.run(cfg, day="2026-11-13", out=tmp_path, no_llm=False, size=6, fixtures=FIXTURES, batch=False)
    assert code == 1 and client.calls == [] and client.batch_requests == []


def test_compare_writes_markdown_with_costs(cfg, tmp_path, monkeypatch):
    import arxiv_digest.cli as cli
    import arxiv_digest.compare as cmp

    text = "T\n\nAbs\n\n## Introduction\n\n" + "intro " * 300 + "\n\n## Model\n\n" + "model " * 300 + "\n\n## Results\n\nwith a quote inside"
    monkeypatch.setattr(cli, "fetch_fulltext", lambda p, **kw: (text, "html", False))
    monkeypatch.setattr(
        cmp, "LLM", lambda c, path, day, hard_cap_usd: LLM(c, path, day, client=FakeClient(), hard_cap_usd=hard_cap_usd)
    )
    monkeypatch.setattr(cmp, "REPO_ROOT", tmp_path)
    code = cmp.compare(
        cfg, day="2026-11-13", out=tmp_path / "out", fixtures=FIXTURES, n=2, max_usd=5.0,
        labels=["haiku", "opus"], sections_for=["haiku"], batch_check=True,
    )
    md = (tmp_path / "comparison" / "2026-11-13.md").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "comparison" / "2026-11-13.json").read_text(encoding="utf-8"))
    assert code == 0
    assert [(r["label"], r["mode"], r["n_done"]) for r in data["runs"]] == [
        ("haiku", "complet", 2), ("opus", "complet", 2), ("haiku", "sections", 2)
    ]
    assert data["runs"][1]["stats"]["usd"] > data["runs"][0]["stats"]["usd"]
    assert "## Coûts mesurés" in md and "vérifié du premier coup" in md and "Mode Batches validé" in md
    assert md.count("### opus — texte complet") == 2
