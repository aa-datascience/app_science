"""Cas partagés avec le portage TypeScript (supabase/functions/open-paper/figures.test.ts)."""

import json
from pathlib import Path

import pytest

from arxiv_digest.figures import figures_for_prompt, valid_labels
from arxiv_digest.models import Figure

CASES = json.loads((Path(__file__).parent / "fixtures" / "figure_cases.json").read_text(encoding="utf-8"))
FIGURES = [Figure(label=f["label"], caption=f["caption"], images=["u"]) for f in CASES["figures"]]


def test_figures_for_prompt():
    assert figures_for_prompt(FIGURES) == CASES["prompt"]
    assert figures_for_prompt([]) == "(no figures available)"
    long = figures_for_prompt([Figure(label="1", caption="é" * CASES["long_caption_chars"], images=["u"])])
    assert long == "[1] " + "é" * 700 + "…"


@pytest.mark.parametrize("case", CASES["labels"], ids=lambda c: f"{c['chosen']}-{c['limit']}")
def test_valid_labels(case):
    assert valid_labels(case["chosen"], FIGURES, case["limit"]) == case["expected"]
