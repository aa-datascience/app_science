"""Tests sans réseau ni appel à l'API Claude."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from arxiv_digest.arxiv import new_submissions, parse_feed
from arxiv_digest.config import load_config
from arxiv_digest.fulltext import html_to_text, latex_to_text
from arxiv_digest.llm import LLM, BudgetExceeded
from arxiv_digest.models import Candidate, Claim, GeneratedContent, Paper, RankBatch, Ranked, RankItem
from arxiv_digest.prefilter import category_score, keyword_score, select_candidates
from arxiv_digest.profile import update_category_weights
from arxiv_digest.scoring import score_all, select_edition
from arxiv_digest.steps import load_prompt, missing_quotes, rank

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def cfg():
    return load_config()


def paper(i, cats=("quant-ph",), title="A paper", abstract="An abstract", authors=("A. Author",)):
    return Paper(arxiv_id=f"2611.{i:05d}", title=title, authors=list(authors), abstract=abstract, categories=list(cats))


def ranked(i, cats=("quant-ph",), rel=3, imp=3, nov=3, slot="main", pre=1.0):
    return Ranked(
        candidate=Candidate(paper=paper(i, cats), prefilter_score=pre, slot=slot),
        rank=RankItem(arxiv_id=f"2611.{i:05d}", relevance=rel, importance=imp, novelty=nov, difficulty=3, why="w"),
    )


# ---------- ingestion ----------


def test_parse_real_feed():
    papers = parse_feed((FIXTURES / "atom_cond-mat.supr-con.xml").read_text(encoding="utf-8"))
    assert len(papers) == 29
    first = papers[0]
    assert first.arxiv_id == "2611.14597" and first.version == 1
    assert first.title.startswith("Little-Parks Oscillations")
    assert first.authors == ["Iogann Tolbatov", "Luca Salasnich"]
    assert first.primary_category == "cond-mat.supr-con"
    assert first.abstract.startswith("We analytically investigate") and "Announce Type" not in first.abstract


def test_new_submissions_excludes_replacements_and_dedupes():
    papers = parse_feed((FIXTURES / "atom_cond-mat.supr-con.xml").read_text(encoding="utf-8"))
    fresh = new_submissions(papers + papers)
    assert len(fresh) == 21  # 10 new + 11 cross ; les 8 replace sont exclus
    assert {p.announce_type for p in fresh} == {"new", "cross"}


# ---------- présélection ----------


def test_keyword_score_title_counts_double_and_negative_subtracts():
    p = paper(1, title="Superconductivity in X", abstract="we study a topological phase; machine learning")
    assert keyword_score(p, {"superconduct": 1.0, "topological": 0.5}, {"machine learning": 1.0}) == 2.0 + 0.5 - 1.0


def test_category_score_crosslist_is_discounted():
    followed = {"quant-ph": 1.0, "hep-th": 0.5}
    assert category_score(paper(1, ("quant-ph", "hep-th")), followed) == 1.0
    assert category_score(paper(1, ("math-ph", "quant-ph")), followed) == 0.7
    assert category_score(paper(1, ("math-ph",)), followed) == 0.0


def test_select_candidates_slots_seen_and_limits(cfg):
    cfg.prefilter.max_candidates = 2
    cfg.prefilter.max_exploration_candidates = 1
    cfg.prefilter.followed_authors = ["Jane Doe"]
    papers = [
        paper(1),
        paper(2, authors=("Jane Doe",)),
        paper(3),
        paper(4),
        paper(5, ("physics.optics",)),
        paper(6, ("physics.optics",)),
    ]
    out = select_candidates(papers, cfg, seen_ids={"2611.00003"}, seed="d")
    main = [c for c in out if c.slot == "main"]
    assert [c.slot for c in out].count("exploration") == 1
    assert len(main) == 2 and main[0].paper.arxiv_id == "2611.00002"  # auteur suivi en tête
    assert "2611.00003" not in {c.paper.arxiv_id for c in out}


# ---------- score et sélection ----------


def test_final_score_bounds(cfg):
    best, worst = score_all([ranked(1, rel=5, imp=5, nov=5, pre=2.0), ranked(2, rel=1, imp=1, nov=1, pre=0.0)], cfg)
    assert best.final_score == pytest.approx(sum(cfg.scoring.weights.values()))
    assert worst.final_score == 0.0


def test_select_edition_diversity_and_exploration(cfg):
    cfg.edition.max_per_category = 2
    pool = [ranked(i, ("quant-ph",), rel=5) for i in range(1, 6)]
    pool += [ranked(i, ("hep-th",), rel=2) for i in range(6, 9)]
    pool += [ranked(9, ("physics.optics",), imp=5, slot="exploration"), ranked(10, ("nucl-th",), imp=1, slot="exploration")]
    sel = select_edition(score_all(pool, cfg), cfg, size=5)
    cats = [r.candidate.paper.primary_category for r in sel]
    assert len(sel) == 5
    assert cats.count("quant-ph") == 2 and cats.count("hep-th") == 2
    assert sel[-1].candidate.slot == "exploration" and sel[-1].candidate.paper.arxiv_id == "2611.00009"


def test_select_edition_relaxes_diversity_when_pool_is_small(cfg):
    cfg.edition.max_per_category = 1
    sel = select_edition(score_all([ranked(i) for i in range(1, 4)], cfg), cfg, size=3)
    assert len(sel) == 3  # pas d'exploration disponible : complété en principal


# ---------- profil ----------


def test_profile_update_moves_then_decays_and_clamps():
    w = update_category_weights({"quant-ph": 1.0, "hep-th": 1.5, "gr-qc": 2.0}, [("quant-ph", "interesting"), ("gr-qc", "saved"), ("nucl-th", "saved")])
    assert w["quant-ph"] == pytest.approx(1.05 - 0.05 * 0.02)
    assert w["hep-th"] == pytest.approx(1.49)  # sans feedback : retour vers 1.0
    assert w["gr-qc"] == 2.0  # plafonné
    assert "nucl-th" not in w


# ---------- texte complet ----------


def test_html_to_text_keeps_math_as_latex_and_drops_bibliography():
    html = (
        '<html><body><nav>menu</nav><article class="ltx_document"><p>Energy <math alttext="E=mc^2" display="inline">'
        '<mi>E</mi></math> holds.</p><section class="ltx_bibliography">Refs</section></article></body></html>'
    )
    text = html_to_text(html)
    assert "$E=mc^2$" in text and "Refs" not in text and "menu" not in text


def test_latex_to_text_expands_inputs_and_strips_comments():
    files = {
        "main.tex": "\\documentclass{article}\n\\begin{document}\nIntro % secret\n\\input{sec}\n\\bibliography{refs}\nafter",
        "sec.tex": "Section body with 5\\% loss",
    }
    text = latex_to_text(files)
    assert "Section body with 5\\% loss" in text and "secret" not in text and "after" not in text


# ---------- vérification et appels au modèle (client factice) ----------


def content_with(quotes):
    return GeneratedContent.model_validate(
        {
            "card": {"plain_title": "t", "finding": "f", "why_it_matters": "w", "tags": [], "difficulty": 9, "reading_minutes": 3},
            "explanation_lay": "l",
            "explanation_expert": "e",
            "context": {"before": "b", "change": "c", "limitations": "l"},
            "claims": [Claim(statement="s", quote=q) for q in quotes],
        }
    )


def test_missing_quotes_ignores_whitespace_and_case():
    c = content_with(["the gap  closes\nat Tc", "an invented sentence"])
    assert c.card.difficulty == 5  # borné à 1-5
    assert missing_quotes(c, "We find that The gap closes at Tc in all samples.") == ["an invented sentence"]


class FakeClient:
    def __init__(self, outputs):
        self.outputs, self.calls = list(outputs), []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(input_tokens=1_000_000, output_tokens=0, cache_creation_input_tokens=0, cache_read_input_tokens=0)
        return SimpleNamespace(parsed_output=self.outputs.pop(0), stop_reason="end_turn", usage=usage)


def test_rank_maps_results_and_logs_cost(cfg, tmp_path):
    cands = [Candidate(paper=paper(1), prefilter_score=1.0), Candidate(paper=paper(2), prefilter_score=0.5)]
    item = RankItem(arxiv_id="2611.00001", relevance=4, importance=3, novelty=3, difficulty=2, why="w")
    stray = RankItem(arxiv_id="9999.99999", relevance=4, importance=3, novelty=3, difficulty=2, why="w")
    client = FakeClient([RankBatch(items=[item, stray])])
    llm = LLM(cfg, tmp_path / "usage.jsonl", "2026-11-13", client=client)
    out = rank(llm, cands, cfg)
    assert [r.candidate.paper.arxiv_id for r in out] == ["2611.00001"]  # id inconnu ignoré, article 2 sans note
    assert "[exploration]" not in client.calls[0]["messages"][0]["content"].split("Papers:")[1]
    assert llm.spent == pytest.approx(cfg.budget.prices[cfg.models.rank][0])
    assert LLM(cfg, tmp_path / "usage.jsonl", "2026-11-13", client=client).spent == pytest.approx(llm.spent)


def test_budget_cap_blocks_calls(cfg, tmp_path):
    cfg.budget.daily_usd = 0.0
    llm = LLM(cfg, tmp_path / "usage.jsonl", "2026-11-13", client=FakeClient([]))
    with pytest.raises(BudgetExceeded):
        llm.parse(step="rank", model=cfg.models.rank, system="s", content="c", schema=RankBatch)


def test_prompts_exist_and_are_versioned():
    for name in ("system", "rank", "generate", "verify"):
        text, version = load_prompt(name)
        assert text and len(version) == 10
