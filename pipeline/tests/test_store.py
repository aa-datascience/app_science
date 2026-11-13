"""Stockage local et Supabase (API REST simulée, aucun réseau)."""

import json

import httpx
from test_llm import TEXT
from test_pipeline import paper

from arxiv_digest.models import Candidate, Card, Claim, Context, Detail, Edition, EditionItem, Ranked, RankItem, StoredDetail
from arxiv_digest.steps import Article
from arxiv_digest.store import LocalStore, SupabaseStore, make_store, server_config


def ranked(i, slot="main"):
    return Ranked(
        candidate=Candidate(paper=paper(i), prefilter_score=1.5, slot=slot),
        rank=RankItem(arxiv_id=f"2611.{i:05d}", relevance=4, importance=3, novelty=3, difficulty=2, why="w"),
        final_score=0.6,
    )


def night(cfg):
    """Une nuit : 3 articles classés, 2 dans l'édition."""
    rk = [ranked(1), ranked(2, "exploration"), ranked(3)]
    card = Card(plain_title="t", finding="f", why_it_matters="w", tags=["a"], difficulty=2)
    items = [
        EditionItem(position=n + 1, slot=r.candidate.slot, paper=r.candidate.paper, rank=r.rank,
                    final_score=r.final_score, card=card, model=cfg.models.card, prompt_version="v1")
        for n, r in enumerate(rk[:2])
    ]
    edition = Edition(date="2026-11-13", status="ready", items=items, cost_usd=0.0165, notes=["n"])
    arts = {i.paper.arxiv_id: Article(i.paper, TEXT, "html") for i in items}
    return edition, rk, arts


def stored_detail():
    d = Detail(explanation_lay="l", explanation_expert="e", context=Context(before="b", change="c", limitations="l"),
               claims=[Claim(statement="s", quote="q")])
    return StoredDetail(arxiv_id="2611.00001", detail=d, removed_claims=[], verification_status="verified",
                        text_source="html", based_on_abstract=False, model="m", prompt_version="v")


class FakeRest:
    """Enregistre les requêtes ; répond aux lectures à partir de `tables`."""

    def __init__(self, tables=None):
        self.requests, self.tables = [], tables or {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        table = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content) if request.content else None
        self.requests.append({"method": request.method, "table": table, "params": dict(request.url.params),
                              "prefer": request.headers.get("prefer", ""), "body": body})
        if request.method == "GET":
            rows = self.tables.get(table, [])
            offset = int(request.url.params.get("offset", 0))
            return httpx.Response(200, json=rows[offset : offset + 1000])
        return httpx.Response(201)

    def store(self, tmp_path):
        client = httpx.Client(base_url="https://x.supabase.co/rest/v1", transport=httpx.MockTransport(self))
        return SupabaseStore("https://x.supabase.co", "key", tmp_path, client=client)


def test_make_store_picks_supabase_only_when_configured(tmp_path, monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    assert isinstance(make_store(tmp_path), LocalStore)
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    assert isinstance(make_store(tmp_path), SupabaseStore)


def test_local_store_roundtrip(cfg, tmp_path):
    store = LocalStore(tmp_path)
    edition, rk, arts = night(cfg)
    store.save_night(cfg, edition, rk, arts)
    assert store.seen_ids() == {"2611.00001", "2611.00002"}
    assert [r.candidate.paper.arxiv_id for r in store.reserve("2026-11-14")] == ["2611.00003"]
    assert store.reserve("2026-11-30") == []  # plus de 7 jours
    assert store.find_paper("2611.00002").title == "A paper" and store.find_paper("nope") is None
    assert store.get_detail("2611.00001") is None
    store.save_detail(stored_detail())
    assert store.get_detail("2611.00001").verification_status == "verified"
    store.log_usage({"date": "2026-11-13", "cost_usd": 0.5})
    store.log_usage({"date": "2026-10-31", "cost_usd": 9.0})
    assert store.usage_rows("2026-11-20") == [{"date": "2026-11-13", "cost_usd": 0.5}]


def test_supabase_night_writes_in_foreign_key_order_and_marks_ready_last(cfg, tmp_path):
    rest = FakeRest()
    edition, rk, arts = night(cfg)
    rest.store(tmp_path).save_night(cfg, edition, rk, arts)
    seq = [(r["method"], r["table"]) for r in rest.requests]
    assert seq == [
        ("POST", "papers"), ("POST", "papers"), ("POST", "rankings"), ("POST", "editions"),
        ("DELETE", "edition_items"), ("POST", "edition_items"), ("POST", "cards"),
        ("POST", "server_config"), ("PATCH", "editions"),
    ]
    posts = [r for r in rest.requests if r["method"] == "POST"]
    assert all("resolution=merge-duplicates" in r["prefer"] for r in posts)  # relancer une nuit ne duplique rien
    assert len(posts[0]["body"]) == 3 and "full_text" not in posts[0]["body"][0]  # tous les articles classés
    assert len(posts[1]["body"]) == 2 and posts[1]["body"][0]["full_text"] == TEXT  # texte : édition seulement
    assert all(len({tuple(sorted(row)) for row in r["body"]}) == 1 for r in posts)  # mêmes clés par lot
    assert posts[3]["body"][0]["status"] == "pending"
    assert rest.requests[-1]["body"]["status"] == "ready" and "ready_at" in rest.requests[-1]["body"]
    assert rest.requests[4]["params"] == {"edition_date": "eq.2026-11-13"}
    config = posts[-1]["body"][0]["config"]
    assert config["detail_model"] == cfg.models.generate and "{{source_note}}" in config["prompts"]["detail"]
    assert config["detail_schema"]["properties"]["claims"]["type"] == "array"
    assert (tmp_path / "editions" / "2026-11-13.json").exists()  # copie locale


def test_supabase_reads(cfg, tmp_path):
    p = {"arxiv_id": "2611.00001", "version": 2, "title": "T", "authors": ["A"], "abstract": "abs",
         "categories": ["quant-ph"], "published": "", "full_text": "stored text", "text_source": "latex",
         "text_mode": "sections", "text_truncated": False}
    rk = {"paper_id": "2611.00001", "date": "2026-11-12", "slot": "main", "prefilter_score": 1.0, "relevance": 4,
          "importance": 3, "novelty": 2, "difficulty": 5, "why": "w", "final_score": 0.5, "papers": p}
    rest = FakeRest({
        "edition_items": [{"paper_id": f"id{i}"} for i in range(1500)],
        "api_usage": [{"date": "2026-11-02", "step": "card", "model": "m", "cost_usd": "0.25"}],
        "rankings": [rk, {**rk, "date": "2026-11-10"}],
        "papers": [p],
        "details": [],
    })
    store = rest.store(tmp_path)
    assert len(store.seen_ids()) == 1500  # pagination au-delà de 1000 lignes
    assert store.usage_rows("2026-11-13")[0]["cost_usd"] == 0.25
    usage_req = next(r for r in rest.requests if r["table"] == "api_usage")
    assert usage_req["params"]["date"] == "gte.2026-11-01" and usage_req["params"]["and"] == "(date.lt.2026-12-01)"
    reserve = store.reserve("2026-11-13")
    assert len(reserve) == 1 and reserve[0].rank.difficulty == 5 and reserve[0].candidate.paper.version == 2
    art = store.article(store.find_paper("2611.00001"))
    assert (art.text, art.source, art.mode) == ("stored text", "latex", "sections")
    assert store.get_detail("2611.00001") is None


def test_supabase_detail_and_usage_writes(cfg, tmp_path):
    rest = FakeRest()
    store = rest.store(tmp_path)
    store.save_detail(stored_detail())
    store.log_usage({"date": "2026-11-13", "step": "detail", "model": "m", "cost_usd": 0.006})
    detail, usage = rest.requests
    assert detail["table"] == "details" and detail["body"][0]["paper_id"] == "2611.00001"
    assert "arxiv_id" not in detail["body"][0] and detail["params"] == {"on_conflict": "paper_id"}
    assert usage["table"] == "api_usage" and usage["body"]["step"] == "detail"
    assert server_config(cfg)["monthly_usd"] == cfg.budget.monthly_usd
