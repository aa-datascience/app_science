// Mêmes cas que pipeline/tests/test_citation_cases.py.
// Lancer depuis la racine du dépôt :  node --test supabase/functions/open-paper/citations.test.ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { checkClaims, normalize } from "./citations.ts";

const cases = JSON.parse(
  readFileSync(new URL("../../../pipeline/tests/fixtures/citation_cases.json", import.meta.url), "utf-8"),
);

test("normalize", () => {
  for (const [input, expected] of cases.normalize) assert.equal(normalize(input), expected);
});

for (const c of cases.claims) {
  test(`checkClaims: ${c.name}`, () => {
    const claims = c.quotes.map((quote: string, i: number) => ({ statement: `s${i}`, quote }));
    const { kept, removed, status } = checkClaims(claims, cases.text);
    assert.deepEqual(removed.map((r) => claims.indexOf(r)), c.removed);
    assert.equal(kept.length, claims.length - c.removed.length);
    assert.equal(status, c.status);
  });
}
