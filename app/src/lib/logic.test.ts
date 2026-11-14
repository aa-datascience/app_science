// Lancer avec : npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildMathHtml,
  editionLabel,
  emptyState,
  figureImages,
  figuresFor,
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

test("figures : copie du stockage si elle existe, sinon adresse d'origine", () => {
  const row = {
    paper_id: "p", label: "2", position: 1, caption: "c", roles: ["card" as const], what_to_look_at: null,
    sources: ["https://arxiv.org/html/p/a.png", "eprint:b.pdf"], storage_paths: ["p/2-1.webp"], stored: true,
  };
  assert.deepEqual(figureImages(row, { "p/2-1.webp": "https://x/signed?token=1" }), [
    { uri: "https://x/signed?token=1", cacheKey: "figures/p/2-1.webp" },
  ]);
  // Pas encore copiée : l'adresse arXiv ; les fichiers de l'archive LaTeX ne sont pas affichables.
  assert.deepEqual(figureImages({ ...row, stored: false, storage_paths: [] }, {}), [
    { uri: "https://arxiv.org/html/p/a.png", cacheKey: "https://arxiv.org/html/p/a.png" },
  ]);
  assert.deepEqual(figureImages(row, {}), []); // copiée mais signature indisponible : rien à afficher
});

test("figures : une pour la carte, celles du détail dans l'ordre du modèle", () => {
  const img = [{ uri: "u", cacheKey: "k" }];
  const f = (label: string, position: number, roles: ("card" | "detail")[], images = img) => ({
    paper_id: "p", label, position, caption: "c", roles, what_to_look_at: null, images,
  });
  const all = [f("1", 0, ["detail"]), f("2", 1, ["card", "detail"]), f("3", 2, ["detail"], []), f("4", 3, [])];
  const { card, detail } = figuresFor(all, [{ label: "2" }, { label: "1" }]);
  assert.equal(card?.label, "2");
  assert.deepEqual(detail.map((x) => x.label), ["2", "1"]); // la 3 n'a pas d'image, la 4 pas de rôle
  assert.equal(figuresFor([f("4", 3, [])]).card, null);
});
