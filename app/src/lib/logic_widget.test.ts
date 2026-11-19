// Widget d'écran d'accueil : série et lectures par jour. Lancer avec : npm test
import assert from "node:assert/strict";
import { test } from "node:test";

import { weekdayInitial, widgetData } from "./logic.ts";
import type { ReadingState, WidgetDay } from "./types.ts";

const day = (date: string, read: number, done: boolean): WidgetDay => ({ date, size: 8, read, done });

test("la série compte les éditions terminées d'affilée ; celle du jour en cours ne la casse pas", () => {
  const days = [day("2026-11-15", 2, true), day("2026-11-18", 0, false), day("2026-11-17", 4, true), day("2026-11-16", 1, true), day("2026-11-14", 3, false)];
  const w = widgetData(days);
  assert.equal(w.streak, 3);
  assert.equal(w.today?.date, "2026-11-18");
  assert.deepEqual(w.days.map((d) => d.date), ["2026-11-14", "2026-11-15", "2026-11-16", "2026-11-17", "2026-11-18"]);
  // Une édition passée non terminée casse la série ; celle du jour terminée la prolonge.
  assert.equal(widgetData([day("2026-11-18", 8, true), day("2026-11-17", 0, false), day("2026-11-16", 2, true)]).streak, 1);
  assert.equal(widgetData([]).today, null);
});

test("l'état local complète la base avant l'envoi de la file d'attente", () => {
  const local: ReadingState = { date: "2026-11-18", shown: [], opened: ["a", "b"], feedback: {}, index: 7, completed: true };
  const w = widgetData([day("2026-11-18", 1, false), day("2026-11-17", 3, true)], local);
  assert.deepEqual(w.today, { date: "2026-11-18", size: 8, read: 2, done: true });
  assert.equal(w.streak, 2);
  const seen: ReadingState = { ...local, shown: ["a", "b", "c", "d", "e", "f", "g", "h"], completed: false };
  assert.equal(widgetData([day("2026-11-18", 0, false)], seen).today?.done, true); // toutes les cartes vues
  assert.equal(widgetData(Array.from({ length: 10 }, (_, i) => day(`2026-11-${10 + i}`, 1, true))).days.length, 7);
});

test("initiale du jour", () => {
  assert.equal(weekdayInitial("2026-11-16"), "M");
  assert.equal(weekdayInitial("2026-11-15"), "S");
});
