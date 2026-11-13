"""Cas partagés avec le portage TypeScript (supabase/functions/open-paper/citations.test.ts)."""

import json
from pathlib import Path

import pytest

from arxiv_digest.citations import check_claims, normalize
from arxiv_digest.models import Claim, Context, Detail

CASES = json.loads((Path(__file__).parent / "fixtures" / "citation_cases.json").read_text(encoding="utf-8"))


def test_normalize():
    for text, expected in CASES["normalize"]:
        assert normalize(text) == expected


@pytest.mark.parametrize("case", CASES["claims"], ids=lambda c: c["name"])
def test_check_claims(case):
    claims = [Claim(statement=f"s{i}", quote=q) for i, q in enumerate(case["quotes"])]
    detail = Detail(
        explanation_lay="l", explanation_expert="e", context=Context(before="b", change="c", limitations="l"), claims=claims
    )
    checked, removed, status = check_claims(detail, CASES["text"])
    assert [claims.index(r) for r in removed] == case["removed"]
    assert len(checked.claims) == len(claims) - len(case["removed"])
    assert status == case["status"]
