// V2, étape 4 : concepts et questions. Lancer avec : npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { conceptName, filterConcepts, isRightOption, lastAttempts, questionsLine, shuffledOptions } from "./logic.ts";
import type { ConceptCard } from "./types.ts";

const card = (id: string, name: string, simple = ""): ConceptCard => ({
  id, name, simple_definition: simple, expert_definition: "", primary_category: "", first_paper_id: null,
  created_at: "", paper_count: 1, papers: [], related: [],
});

test("QCM : juste seulement pour l'option exacte", () => {
  assert.equal(isRightOption({ answer: "Andreev bound states" }, "Andreev bound states"), true);
  assert.equal(isRightOption({ answer: "Andreev bound states" }, "Phonons"), false);
});

test("dernière réponse par question", () => {
  const last = lastAttempts([
    { question_id: 1, answer: "b", correct: false, created_at: "2026-11-20T10:00:00Z" },
    { question_id: 1, answer: "a", correct: true, created_at: "2026-11-20T09:00:00Z" },
  ]);
  assert.equal(last[1].answer, "b");
});

test("recherche de concepts, ordre alphabétique, nom d'un lien", () => {
  const all = [card("b", "Josephson effect", "tunnel"), card("a", "Andreev reflection")];
  assert.deepEqual(filterConcepts(all, "").map((c) => c.id), ["a", "b"]);
  assert.deepEqual(filterConcepts(all, "TUNNEL").map((c) => c.id), ["b"]);
  assert.equal(conceptName(all, "a"), "Andreev reflection");
  assert.equal(conceptName(all, "gone"), "gone");
  assert.equal(questionsLine(4, 3), "3/4");
  assert.equal(questionsLine(0, 0), "–");
});

test("options mélangées : stables pour une question, complètes, bonne réponse pas toujours en tête", () => {
  const opts = ["right", "b", "c", "d"];
  assert.deepEqual(shuffledOptions(opts, 7), shuffledOptions(opts, 7));
  assert.deepEqual([...shuffledOptions(opts, 7)].sort(), [...opts].sort());
  const firsts = new Set(Array.from({ length: 20 }, (_, i) => shuffledOptions(opts, i + 1)[0]));
  assert.ok(firsts.size > 1);
});
