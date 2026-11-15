// V2 : carnet, statistiques, profil. Lancer avec : npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allTags,
  bibKey,
  describeChange,
  filterNotebook,
  isMonday,
  lastChanges,
  parseTags,
  percent,
  profileDiff,
  shiftTime,
  stepWeight,
  summaryFor,
  toBibtex,
  toMarkdown,
} from "./logic.ts";
import type { Level, NotebookEntry, Weight } from "./types.ts";

const entry = (over: Partial<NotebookEntry> = {}): NotebookEntry => ({
  paper_id: "2611.01234",
  note: "",
  tags: [],
  saved_at: "2026-11-14T08:00:00Z",
  title: "The Josephson diode effect in a $\\varphi_0$ junction",
  authors: ["Élise Müller", "Jo Tanaka"],
  categories: ["cond-mat.supr-con", "quant-ph"],
  primary_category: "cond-mat.supr-con",
  plain_title: "A superconducting one-way street",
  finding: "They measured a nonreciprocal supercurrent.",
  ...over,
});

test("tags : saisis séparés par des virgules, sans doublon", () => {
  assert.deepEqual(parseTags(" Superconductivity, to  read ,, superconductivity"), ["superconductivity", "to read"]);
  assert.deepEqual(allTags([entry({ tags: ["b", "a"] }), entry({ tags: ["a"] })]), ["a", "b"]);
});

test("recherche du carnet : tous les mots, dans la note, les titres, les auteurs ou les tags", () => {
  const all = [entry(), entry({ paper_id: "2611.00002", title: "Cold atoms", authors: ["A B"], note: "ask Müller", tags: ["thesis"], plain_title: null, finding: null })];
  assert.equal(filterNotebook(all, "", null).length, 2);
  assert.deepEqual(filterNotebook(all, "joseph diode", null).map((e) => e.paper_id), ["2611.01234"]);
  assert.equal(filterNotebook(all, "müller", null).length, 2); // auteur de l'un, note de l'autre
  assert.deepEqual(filterNotebook(all, "", "thesis").map((e) => e.paper_id), ["2611.00002"]);
  assert.equal(filterNotebook(all, "joseph", "thesis").length, 0);
});

test("export Markdown", () => {
  const md = toMarkdown([entry({ note: " Compare with Fig. 2 of the review.\n", tags: ["diode"] })]);
  assert.ok(md.startsWith("# Notebook\n\n## The Josephson diode effect"));
  assert.ok(md.includes("[arXiv:2611.01234](https://arxiv.org/abs/2611.01234)"));
  assert.ok(md.includes("Tags: diode") && md.includes("### Notes\n\nCompare with Fig. 2 of the review."));
  assert.ok(md.includes("Saved on 2026-11-14"));
  assert.ok(!toMarkdown([entry()]).includes("### Notes")); // pas de section vide
});

test("export BibTeX", () => {
  assert.equal(bibKey(entry()), "muller2026josephson");
  const bib = toBibtex([entry(), entry({ paper_id: "2611.09999" })]);
  assert.ok(bib.includes("@misc{muller2026josephson,") && bib.includes("@misc{muller2026josephsonb,")); // clés uniques
  assert.ok(bib.includes("author = {Élise Müller and Jo Tanaka}"));
  assert.ok(bib.includes("eprint = {2611.01234}") && bib.includes("primaryClass = {cond-mat.supr-con}"));
  assert.ok(bib.includes("title = {{The Josephson diode effect in a $\\varphi_0$ junction}}"));
  assert.equal(bibKey(entry({ authors: [], title: "On the" })), "arxiv2026");
});

test("bilan du lundi : le lundi seulement, et s'il y a eu quelque chose", () => {
  const s = { week: "2026-11-09", shown: 20, read: 6, skipped: 14, saved: 2, editions_completed: 3, most_read_category: "quant-ph", most_skipped_category: null };
  assert.equal(isMonday("2026-11-16"), true);
  assert.equal(isMonday("2026-11-14"), false);
  assert.equal(summaryFor("2026-11-16", s), s);
  assert.equal(summaryFor("2026-11-17", s), null);
  assert.equal(summaryFor("2026-11-16", { ...s, shown: 0 }), null);
  assert.equal(summaryFor("2026-11-16", null), null);
  assert.equal(percent(0.333), "33%");
  assert.equal(percent(null), "–");
});

test("réglages : crans des poids et des heures", () => {
  assert.equal(stepWeight(1.0, 1), 1.1);
  assert.equal(stepWeight(1.52, -1), 1.4);
  assert.equal(stepWeight(2.0, 1), 2.0);
  assert.equal(stepWeight(0.2, -1), 0.2);
  assert.equal(stepWeight(-0.5, 1), -0.6); // mot-clé négatif : plus fort, toujours négatif
  assert.equal(shiftTime("07:30", 30, "06:00", "10:00"), "08:00");
  assert.equal(shiftTime("06:00", -30, "06:00", "10:00"), "06:00");
  assert.equal(shiftTime("09:45", 30, "06:00", "10:00"), "10:00");
});

test("profil modifié à la main : écritures et journal", () => {
  const w = (kind: Weight["kind"], key: string, weight: number, locked = false): Weight => ({ kind, key, weight, baseline: 1, locked });
  const before = {
    weights: [w("category", "quant-ph", 1.2), w("category", "hep-th", 1), w("keyword", "vortex", 0.5), w("keyword", "andreev", 2)],
    levels: [{ category: "quant-ph", level: "intermediate", drift: 2, locked: false }] as Level[],
  };
  const after = {
    weights: [w("category", "quant-ph", 1.5), w("keyword", "vortex", 0.5, true), w("keyword", "andreev", 2), w("category", "gr-qc", 1)],
    levels: [
      { category: "quant-ph", level: "expert", drift: 2, locked: false },
      { category: "gr-qc", level: "intermediate", drift: 0, locked: false },
    ] as Level[],
  };
  const d = profileDiff(before, after);
  // La valeur saisie devient la valeur de repos ; un simple verrou ne la touche pas ; « andreev » inchangé.
  assert.deepEqual(d.weights, [
    { kind: "category", key: "quant-ph", weight: 1.5, baseline: 1.5, locked: false },
    { kind: "keyword", key: "vortex", weight: 0.5, baseline: 1, locked: true },
    { kind: "category", key: "gr-qc", weight: 1, baseline: 1, locked: false },
  ]);
  assert.deepEqual(d.removed.map((x) => x.key), ["hep-th"]);
  assert.deepEqual(d.levels, [{ category: "quant-ph", level: "expert", drift: 0, locked: false }]);
  assert.deepEqual(d.changes.map((c) => [c.kind, c.key, c.old_value, c.new_value]), [
    ["category", "quant-ph", "1.200", "1.500"],
    ["category", "gr-qc", null, "1.000"],
    ["category", "hep-th", "1.000", "removed"],
    ["level", "quant-ph", "intermediate", "expert"],
  ]);
  assert.ok(d.changes.every((c) => c.source === "manual"));
  const same = profileDiff(before, before);
  assert.deepEqual([same.weights, same.removed, same.levels, same.changes], [[], [], [], []]);
});

test("dernier changement d'un poids et sa raison", () => {
  const c = (key: string, changed_at: string, reason: string | null) => ({
    kind: "category", key, changed_at, source: "feedback", old_value: "1.000", new_value: "1.050", reason,
  });
  const last = lastChanges([c("quant-ph", "2026-11-14T05:00:00Z", "1 interesting"), c("quant-ph", "2026-11-12T05:00:00Z", "old"), c("hep-th", "2026-11-13T05:00:00Z", null)]);
  assert.equal(describeChange(last["category:quant-ph"]), "14 Nov: 1.000 → 1.050 · 1 interesting");
  assert.equal(describeChange(last["category:hep-th"]), "13 Nov: 1.000 → 1.050");
  assert.equal(describeChange(undefined), "");
});
