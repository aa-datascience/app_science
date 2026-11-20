// Mêmes cas que pipeline/tests/test_learning_cases.py.
// Lancer depuis la racine du dépôt :  node --test supabase/functions/open-paper/learning.test.ts
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { checkQuestions, knownForPrompt, resolveConcepts, slugify } from "./learning.ts";

const cases = JSON.parse(
  readFileSync(new URL("../../../pipeline/tests/fixtures/learning_cases.json", import.meta.url), "utf-8"),
);

test("slugify", () => {
  for (const [input, expected] of cases.slugify) assert.equal(slugify(input), expected);
});

for (const c of cases.questions) {
  test(`checkQuestions: ${c.name}`, () => {
    const { kept, removed } = checkQuestions(c.questions, cases.text);
    assert.deepEqual(kept.map((q) => q.prompt), c.kept.map((i: number) => c.questions[i].prompt.trim()));
    assert.deepEqual(kept.map((q) => q.answer), c.answers);
    assert.equal(kept.length + removed.length, c.questions.length);
    if (c.options) assert.deepEqual(kept.map((q) => q.options), c.options);
  });
}

for (const c of cases.concepts) {
  test(`resolveConcepts: ${c.name}`, () => {
    const out = resolveConcepts(c.entries, c.known);
    assert.deepEqual(out.paper, c.paper);
    assert.deepEqual(out.new.map((n) => n.id), c.new);
    assert.deepEqual(out.links, c.links);
  });
}

test("knownForPrompt", () => {
  const k = cases.known_for_prompt;
  assert.equal(knownForPrompt(k.concepts, k.category, k.limit), k.expected);
  assert.equal(knownForPrompt([], "x"), "(none yet)");
});
