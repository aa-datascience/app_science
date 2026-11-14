"""Appels au modèle, lots, citations, plafond mensuel, bout en bout — avec un client factice."""

import json
from types import SimpleNamespace

import pytest
from test_pipeline import FIXTURES, paper

from arxiv_digest.budget import affordable_size, can_open, estimate_cost, month_spent
from arxiv_digest.citations import check_claims, normalize
from arxiv_digest.fulltext import FullText, select_sections
from arxiv_digest.llm import LLM, BudgetExceeded, read_usage, usage_cost
from arxiv_digest.models import Candidate, Card, Claim, Context, Detail, RankBatch, RankItem
from arxiv_digest.steps import Article, generate_detail, make_article, make_cards, rank

TEXT = (
    "We measure the critical temperature $T_{c}$ of the film and find $T_{c}=9.2$ K. "
    "The supercurrent is carried by Andreev bound states; the gap closes at the transition. "
) * 20


def detail_with(quotes):
    return Detail(
        explanation_lay="l",
        explanation_expert="e",
        context=Context(before="b", change="c", limitations="l"),
        claims=[Claim(statement=f"s{i}", quote=q) for i, q in enumerate(quotes)],
        figures=[],
    )


GOOD = "The supercurrent is carried by Andreev bound states"
BAD = "The authors demonstrate room-temperature superconductivity"


class FakeClient:
    """Client factice : répond selon le schéma demandé. Sert aussi de faux service Batches."""

    def __init__(self, quotes=(GOOD, GOOD, GOOD)):
        self.calls, self.quotes = [], list(quotes)
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
        elif "plain_title" in props:
            out = Card(plain_title="t", finding="f", why_it_matters="w", tags=["a"], difficulty=9, figure="")
        else:
            out = detail_with(self.quotes)
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


def steps_of(client):
    def step(params):
        props = params["output_config"]["format"]["schema"]["properties"]
        return "rank" if "items" in props else "card" if "plain_title" in props else "detail"

    return [step(c) for c in client.calls]


# ---------- vérification des citations, sans modèle ----------


def test_normalize_ignores_case_spaces_punctuation_and_latex_formatting():
    assert normalize("the critical  temperature\n$T_{c}$ = 9.2 K.") == normalize(r"The critical temperature \mathrm{T}_c=9.2\,K")
    assert normalize("ﬁeld") == "field"  # ligature de PDF


def test_check_claims_removes_missing_quotes_and_applies_one_third_rule():
    tolerant = "we measure the critical temperature T_c of the film, and find T_c = 9.2 K"
    d, removed, status = check_claims(detail_with([GOOD, tolerant, BAD]), TEXT)
    assert status == "verified" and [c.quote for c in removed] == [BAD]  # 1 sur 3 : toléré
    assert [c.quote for c in d.claims] == [GOOD, tolerant]
    assert check_claims(detail_with([GOOD, BAD]), TEXT)[2] == "unverified"  # 1 sur 2 : plus d'un tiers
    assert check_claims(detail_with([]), TEXT)[2] == "unverified"  # rien de sourcé
    assert check_claims(detail_with(["the gap"]), TEXT)[2] == "unverified"  # citation trop courte pour prouver


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


def test_cards_use_only_title_and_abstract_and_batches_at_half_price(cfg, tmp_path):
    client = FakeClient()
    llm = make_llm(cfg, tmp_path, client)
    papers = [paper(1, title="Title one", abstract="Abstract one"), paper(2)]
    cards, version = make_cards(llm, papers, cfg, batch=True)
    assert client.calls == [] and [len(b) for b in client.batch_requests] == [2]  # un seul lot, rien en synchrone
    assert set(cards) == {"2611.00001", "2611.00002"} and cards["2611.00001"].difficulty == 5 and len(version) == 10
    params = client.batch_requests[0][0]["params"]
    assert params["model"] == cfg.models.card
    assert "Abstract one" in params["messages"][0]["content"] and "<paper>" not in params["messages"][0]["content"]
    rows = read_usage(tmp_path / "usage.jsonl")
    p_in, p_out = cfg.budget.prices[cfg.models.card][:2]
    assert all(r["batch"] and r["step"] == "card" for r in rows)
    assert rows[0]["cost_usd"] == pytest.approx((1000 * p_in + 100 * p_out) / 1e6 / 2, abs=1e-6)
    make_cards(llm, papers, cfg, batch=False)
    assert steps_of(client) == ["card", "card"]


def test_detail_is_one_call_and_checks_quotes_without_model(cfg, tmp_path):
    client = FakeClient(quotes=[GOOD, GOOD, GOOD, BAD])
    stored = generate_detail(make_llm(cfg, tmp_path, client), Article(paper(1), TEXT, "html"), cfg, label="x")
    assert steps_of(client) == ["detail"]  # ni vérification ni correction par le modèle
    assert client.calls[0]["model"] == cfg.models.generate
    assert TEXT in client.calls[0]["messages"][0]["content"][0]["text"]
    assert stored.verification_status == "verified"
    assert len(stored.detail.claims) == 3 and [c.quote for c in stored.removed_claims] == [BAD]
    bad = generate_detail(make_llm(cfg, tmp_path, FakeClient(quotes=[GOOD, BAD])), Article(paper(1), TEXT, "html"), cfg)
    assert bad.verification_status == "unverified"


def test_hard_cap_blocks_calls(cfg, tmp_path):
    llm = make_llm(cfg, tmp_path, FakeClient(), hard_cap_usd=0.0)
    with pytest.raises(BudgetExceeded):
        generate_detail(llm, Article(paper(1), TEXT, "html"), cfg)


# ---------- plafond mensuel ----------


def test_affordable_size_spreads_budget_over_remaining_days():
    kw = dict(monthly_cap=15.0, per_article=0.10, fixed=0.0)
    assert affordable_size(8, spent=0.0, day="2026-11-01", **kw) == 5  # 15 $ / 30 jours = 0,50 $ par jour
    assert affordable_size(8, spent=0.0, day="2026-11-30", **kw) == 8  # dernier jour : tout le reste
    assert affordable_size(8, spent=14.95, day="2026-11-13", **kw) == 0
    assert affordable_size(8, spent=20.0, day="2026-11-13", **kw) == 0
    assert can_open(monthly_cap=15.0, spent=14.9, estimate=0.1) and not can_open(monthly_cap=15.0, spent=14.95, estimate=0.1)


def test_estimate_cost_uses_history_else_prices(cfg):
    cfg.models.generate = "claude-sonnet-5-5"
    t_in, t_out = cfg.budget.assumed_tokens["detail"]
    assert estimate_cost(cfg, [], "detail") == pytest.approx((t_in * 2 + t_out * 10) / 1e6)
    day = {"date": "2026-11-12"}
    rows = [
        {**day, "step": "detail", "model": "claude-sonnet-5-5", "cost_usd": 0.2},
        {**day, "step": "detail", "model": "claude-sonnet-5-5", "cost_usd": 0.1},
        {**day, "step": "detail", "model": "claude-sonnet-5-5", "cost_usd": 9.0, "mode": "sections"},
        {**day, "step": "detail", "model": "claude-opus-5-5", "cost_usd": 9.0},
        {**day, "step": "card", "model": cfg.models.card, "cost_usd": 0.001, "batch": True},
    ]
    assert estimate_cost(cfg, rows, "detail") == pytest.approx(0.15)
    assert estimate_cost(cfg, rows, "card") == pytest.approx(0.002)  # ramené au prix synchrone
    assert estimate_cost(cfg, rows, "card", batch=True) == pytest.approx(0.001)


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


@pytest.fixture
def fake_cli(cfg, monkeypatch):
    import arxiv_digest.cli as cli

    client = FakeClient()
    monkeypatch.setattr(cli, "fetch_fulltext", lambda p, **kw: FullText(TEXT, "html"))
    monkeypatch.setattr(cli, "LLM", lambda c, path, day: LLM(c, path, day, client=client))
    return cli, client


def test_night_makes_cards_only_then_open_generates_detail_once(cfg, tmp_path, fake_cli):
    cli, client = fake_cli
    assert cli.run(cfg, day="2026-11-13", out=tmp_path, no_llm=False, size=3, fixtures=FIXTURES, batch=True) == 0
    edition = json.loads((tmp_path / "editions" / "2026-11-13.json").read_text(encoding="utf-8"))
    assert edition["status"] == "ready" and len(edition["items"]) == 3
    assert set(steps_of(client)) == {"rank"} and len(client.batch_requests) == 1  # la nuit : aucun détail
    assert edition["items"][0]["card"]["plain_title"] == "t" and "content" not in edition["items"][0]

    aid = edition["items"][0]["paper"]["arxiv_id"]
    assert cli.open_paper(cfg, day="2026-11-13", out=tmp_path, arxiv_id=aid) == 0
    stored = json.loads((tmp_path / "details" / f"{aid}.json").read_text(encoding="utf-8"))
    assert stored["verification_status"] == "verified" and len(stored["detail"]["claims"]) == 3
    n_calls = len(client.calls)
    assert cli.open_paper(cfg, day="2026-11-13", out=tmp_path, arxiv_id=aid) == 0
    assert len(client.calls) == n_calls  # déjà stocké : jamais régénéré
    assert cli.open_paper(cfg, day="2026-11-13", out=tmp_path, arxiv_id="0000.00000") == 1

    cfg.budget.monthly_usd = 0.0  # plafond atteint : ouverture refusée, sans appel
    other = edition["items"][1]["paper"]["arxiv_id"]
    assert cli.open_paper(cfg, day="2026-11-13", out=tmp_path, arxiv_id=other) == 3
    assert len(client.calls) == n_calls


def test_run_reduces_edition_to_monthly_budget_before_any_call(cfg, tmp_path, fake_cli):
    cli, client = fake_cli
    cfg.budget.monthly_usd = 0.9  # 18 jours restants -> 0,05 $ par jour, dont 0,02 $ de classement
    cfg.budget.prices[cfg.models.card] = [10.0, 0.0]
    cfg.budget.assumed_tokens["card"] = (1000, 0)  # 0,01 $ par carte
    assert cli.run(cfg, day="2026-11-13", out=tmp_path, no_llm=False, size=6, fixtures=FIXTURES, batch=False) == 0
    edition = json.loads((tmp_path / "editions" / "2026-11-13.json").read_text(encoding="utf-8"))
    assert len(edition["items"]) == 3 and "édition réduite de 6 à 3" in edition["notes"][0]

    client.calls.clear()
    cfg.budget.monthly_usd = 0.0
    assert cli.run(cfg, day="2026-11-14", out=tmp_path / "b", no_llm=False, size=6, fixtures=FIXTURES, batch=False) == 1
    assert client.calls == [] and len(client.batch_requests) == 0


def test_compare_measures_night_and_open_costs(cfg, tmp_path, monkeypatch, fake_cli):
    import arxiv_digest.compare as cmp

    monkeypatch.setattr(
        cmp, "LLM", lambda c, path, day, hard_cap_usd: LLM(c, path, day, client=FakeClient(), hard_cap_usd=hard_cap_usd)
    )
    monkeypatch.setattr(cmp, "REPO_ROOT", tmp_path)
    code = cmp.compare(
        cfg, day="2026-11-13", out=tmp_path / "out", fixtures=FIXTURES, n=2, max_usd=2.0,
        detail_labels=["sonnet", "haiku"], batch=True,
    )
    md = (tmp_path / "comparison" / "2026-11-13.md").read_text(encoding="utf-8")
    data = json.loads((tmp_path / "comparison" / "2026-11-13.json").read_text(encoding="utf-8"))
    assert code == 0 and data["cards"]["n_done"] == 2 and data["cards"]["batch"]
    assert [(r["label"], r["n_done"]) for r in data["runs"]] == [("sonnet", 2), ("haiku", 2)]
    assert data["runs"][0]["stats"]["usd"] > data["runs"][1]["stats"]["usd"] > 0
    assert data["total_usd"] == pytest.approx(
        data["ranking"]["usd"] + data["cards"]["stats"]["usd"] + sum(r["stats"]["usd"] for r in data["runs"]), abs=1e-3
    )
    for heading in ("## Coût de la nuit", "## Coût par article ouvert", "## Extrapolation mensuelle"):
        assert heading in md
    assert md.count("### Détail — sonnet") == 2 and "citations retrouvées" in md
