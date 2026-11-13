// Lancer avec : npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildMathHtml,
  editionLabel,
  emptyState,
  markOpened,
  markShown,
  stateFor,
  summarize,
  toggleFeedback,
} from "./logic.ts";

const cards = ["a", "b", "c"].map((arxiv_id) => ({ arxiv_id }));

test("editionLabel", () => {
  assert.equal(editionLabel(8), "8 papers · ~25 min");
  assert.equal(editionLabel(3), "3 papers · ~10 min");
  assert.equal(editionLabel(1), "1 paper · ~3 min");
});

test("l'état d'un autre jour est ignoré", () => {
  const old = { ...emptyState("2026-11-12"), completed: true };
  assert.equal(stateFor("2026-11-13", old).completed, false);
  assert.equal(stateFor("2026-11-12", old).completed, true);
  assert.deepEqual(stateFor("2026-11-13", null), emptyState("2026-11-13"));
});

test("montré, lu, ignoré, sauvegardé", () => {
  let s = emptyState("d");
  s = markShown(s, "a", 0);
  s = markShown(s, "a", 0); // une seule fois
  s = markShown(s, "b", 1);
  s = markOpened(s, "b");
  s = markOpened(s, "c"); // ouvrir compte aussi comme montré
  s = toggleFeedback(s, "c", "saved").state;
  assert.deepEqual(s.shown, ["a", "b", "c"]);
  assert.equal(s.index, 1);
  assert.deepEqual(summarize(cards, s), { total: 3, read: 2, skipped: 1, saved: 1 });
});

test("feedback : paires exclusives, bascule, sauvegarde indépendante", () => {
  let r = toggleFeedback(emptyState("d"), "a", "interesting");
  assert.deepEqual([r.added, r.removed], ["interesting", []]);
  r = toggleFeedback(r.state, "a", "not_interesting");
  assert.deepEqual([r.added, r.removed, r.state.feedback.a], ["not_interesting", ["interesting"], ["not_interesting"]]);
  r = toggleFeedback(r.state, "a", "too_hard");
  r = toggleFeedback(r.state, "a", "saved");
  assert.deepEqual(r.state.feedback.a, ["not_interesting", "too_hard", "saved"]);
  r = toggleFeedback(r.state, "a", "saved"); // second appui : retire
  assert.deepEqual([r.added, r.removed, r.state.feedback.a], [null, ["saved"], ["not_interesting", "too_hard"]]);
});

test("buildMathHtml échappe le texte et garde le LaTeX", () => {
  const html = buildMathHtml("If $a<b$ then <script>alert(1)</script>\n\nSecond & last.", {
    text: "#eee",
    background: "#000",
    muted: "#888",
  });
  assert.ok(html.includes("<p>If $a&lt;b$ then &lt;script&gt;alert(1)&lt;/script&gt;</p><p>Second &amp; last.</p>"));
  assert.ok(!html.includes("<script>alert(1)"));
});
