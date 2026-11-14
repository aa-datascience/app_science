// Mêmes cas que pipeline/tests/test_figure_cases.py.
// Lancer depuis la racine du dépôt :  node --test supabase/functions/open-paper/figures.test.ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { figuresForPrompt, validLabels } from "./figures.ts";

const cases = JSON.parse(
  readFileSync(new URL("../../../pipeline/tests/fixtures/figure_cases.json", import.meta.url), "utf-8"),
);

test("figuresForPrompt", () => {
  assert.equal(figuresForPrompt(cases.figures), cases.prompt);
  assert.equal(figuresForPrompt([]), "(no figures available)");
  const long = figuresForPrompt([{ label: "1", caption: "é".repeat(cases.long_caption_chars) }]);
  assert.equal(long, "[1] " + "é".repeat(700) + "…");
});

for (const c of cases.labels) {
  test(`validLabels ${JSON.stringify(c.chosen)} (max ${c.limit})`, () => {
    assert.deepEqual(validLabels(c.chosen, cases.figures, c.limit), c.expected);
  });
}
