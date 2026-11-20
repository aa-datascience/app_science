// Concepts et questions du détail (V2, étape 4), contrôlés sans appel au modèle.
// Portage à l'identique de pipeline/arxiv_digest/learning.py, avec les mêmes cas de test
// (pipeline/tests/fixtures/learning_cases.json). Toute modification se fait des deux côtés.

import { normalize, quoteFound } from "./citations.ts";

export const MAX_CONCEPTS = 3;
export const MAX_QUESTIONS = 3;
export const MAX_RELATED = 3;
export const MAX_KNOWN = 150; // concepts connus donnés au modèle (décision 5)
const MIN_OPTIONS = 2;
const MAX_OPTIONS = 6;
const MAX_ID_CHARS = 60;

export type Question = {
  kind: "mcq" | "short";
  prompt: string;
  options: string[];
  answer: string;
  explanation: string;
  quote: string;
};

export type ConceptEntry = {
  id?: string;
  name?: string;
  simple_definition?: string;
  expert_definition?: string;
  related?: string[];
};

export type NewConcept = { id: string; name: string; simple_definition: string; expert_definition: string };
export type KnownConcept = { id: string; name: string; primary_category?: string; created_at?: string };

const clean = (s: unknown) => (typeof s === "string" ? s.trim() : "");

/** « Andreev Bound State » ou « andreev_bound-state » -> « andreev-bound-state ». */
export function slugify(s: string): string {
  const out = s.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return out.slice(0, MAX_ID_CHARS).replace(/^-+|-+$/g, "");
}

/** Renvoie les questions gardées (nettoyées) et les questions retirées. Trois gardées au plus. */
export function checkQuestions(questions: Partial<Question>[], text: string): { kept: Question[]; removed: unknown[] } {
  const hay = normalize(text);
  const kept: Question[] = [];
  const removed: unknown[] = [];
  for (const q of questions) {
    const kind = q?.kind;
    const prompt = clean(q?.prompt);
    let answer = clean(q?.answer);
    let ok = kept.length < MAX_QUESTIONS && (kind === "mcq" || kind === "short") && Boolean(prompt) && Boolean(answer);
    ok = ok && quoteFound(clean(q?.quote), hay);
    const options: string[] = [];
    if (ok && kind === "mcq") {
      const seen = new Set<string>();
      for (const raw of Array.isArray(q.options) ? q.options : []) {
        const o = clean(raw);
        if (o && !seen.has(normalize(o))) {
          seen.add(normalize(o));
          options.push(o);
        }
      }
      // La réponse doit être l'une des options ; on garde le texte exact de l'option.
      const match = options.find((o) => normalize(o) === normalize(answer));
      ok = options.length >= MIN_OPTIONS && options.length <= MAX_OPTIONS && match !== undefined;
      answer = match ?? answer;
    }
    if (ok) {
      kept.push({ kind: kind as Question["kind"], prompt, options, answer, explanation: clean(q.explanation), quote: clean(q.quote) });
    } else {
      removed.push(q);
    }
  }
  return { kept, removed };
}

/**
 * Décide, pour les concepts proposés, lesquels réutiliser et lesquels créer.
 * `knownIds` : tous les identifiants déjà en base. Liens en paires [a, b] avec a < b.
 */
export function resolveConcepts(
  entries: ConceptEntry[],
  knownIds: Iterable<string>,
): { paper: string[]; new: NewConcept[]; links: [string, string][] } {
  const known = new Set(knownIds);
  const paper: string[] = [];
  const created: NewConcept[] = [];
  const related = new Map<string, string[]>();
  for (const e of entries) {
    if (paper.length >= MAX_CONCEPTS) break;
    const id = slugify(clean(e?.id) || clean(e?.name));
    if (!id || paper.includes(id)) continue;
    if (!known.has(id)) {
      const name = clean(e.name), simple = clean(e.simple_definition), expert = clean(e.expert_definition);
      if (!(name && simple && expert)) continue; // un identifiant inconnu sans fiche complète ne peut pas être créé
      created.push({ id, name, simple_definition: simple, expert_definition: expert });
    }
    paper.push(id);
    related.set(id, (Array.isArray(e.related) ? e.related : []).map((r) => slugify(clean(r))).slice(0, MAX_RELATED));
  }
  const exists = new Set([...known, ...paper]);
  const links: [string, string][] = [];
  for (const id of paper) {
    for (const r of related.get(id) ?? []) {
      const pair = (id < r ? [id, r] : [r, id]) as [string, string];
      if (r && r !== id && exists.has(r) && !links.some((l) => l[0] === pair[0] && l[1] === pair[1])) links.push(pair);
    }
  }
  return { paper, new: created, links };
}

/** Liste « - id: name » des concepts connus : ceux du même domaine d'abord, puis les plus récents. */
export function knownForPrompt(concepts: KnownConcept[], category: string, limit = MAX_KNOWN): string {
  const at = (c: KnownConcept) => c.created_at ?? "";
  const ordered = [...concepts]
    .sort((x, y) => (at(x) < at(y) ? 1 : at(x) > at(y) ? -1 : 0))
    .sort((x, y) => Number(x.primary_category !== category) - Number(y.primary_category !== category));
  return ordered.slice(0, limit).map((c) => `- ${c.id}: ${c.name}`).join("\n") || "(none yet)";
}
