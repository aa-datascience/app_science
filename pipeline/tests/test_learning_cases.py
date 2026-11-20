"""Cas partagés avec le portage TypeScript (supabase/functions/open-paper/learning.test.ts)."""

import json
from pathlib import Path

import pytest

from arxiv_digest.learning import check_questions, known_for_prompt, resolve_concepts, slugify

CASES = json.loads((Path(__file__).parent / "fixtures" / "learning_cases.json").read_text(encoding="utf-8"))


def test_slugify():
    for text, expected in CASES["slugify"]:
        assert slugify(text) == expected


@pytest.mark.parametrize("case", CASES["questions"], ids=lambda c: c["name"])
def test_check_questions(case):
    kept, removed = check_questions(case["questions"], CASES["text"])
    assert [q["prompt"] for q in kept] == [case["questions"][i]["prompt"].strip() for i in case["kept"]]
    assert [q["answer"] for q in kept] == case["answers"]
    assert len(kept) + len(removed) == len(case["questions"])
    if "options" in case:
        assert [q["options"] for q in kept] == case["options"]


@pytest.mark.parametrize("case", CASES["concepts"], ids=lambda c: c["name"])
def test_resolve_concepts(case):
    out = resolve_concepts(case["entries"], case["known"])
    assert out["paper"] == case["paper"]
    assert [c["id"] for c in out["new"]] == case["new"]
    assert out["links"] == case["links"]


def test_known_for_prompt():
    c = CASES["known_for_prompt"]
    assert known_for_prompt(c["concepts"], c["category"], c["limit"]) == c["expected"]
    assert known_for_prompt([], "x") == "(none yet)"
