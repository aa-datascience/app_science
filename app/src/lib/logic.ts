// Logique pure, sans dépendance à React Native : testée par `npm test` (node --test).

import type {
  AppSettings,
  Attempt,
  ConceptCard,
  EditionCard,
  FeedbackType,
  FigureImage,
  Level,
  NotebookEntry,
  PaperFigure,
  ProfileChange,
  QuestionRow,
  ReadingState,
  WeekSummary,
  Weight,
  WidgetData,
  WidgetDay,
} from "./types.ts";

export const MINUTES_PER_PAPER = 3;

/** « 8 papers · ~25 min » */
export function editionLabel(n: number): string {
  const minutes = Math.max(1, Math.round((n * MINUTES_PER_PAPER) / 5) * 5);
  return `${n} paper${n > 1 ? "s" : ""} · ~${n < 2 ? MINUTES_PER_PAPER : minutes} min`;
}

export function emptyState(date: string): ReadingState {
  return { date, shown: [], opened: [], feedback: {}, index: 0, completed: false };
}

/** L'état gardé sur le téléphone ne vaut que pour l'édition du même jour. */
export function stateFor(date: string, saved: ReadingState | null): ReadingState {
  return saved && saved.date === date ? saved : emptyState(date);
}

const add = (list: string[], id: string) => (list.includes(id) ? list : [...list, id]);

export function markShown(s: ReadingState, id: string, index: number): ReadingState {
  return { ...s, shown: add(s.shown, id), index: Math.max(s.index, index) };
}

export function markOpened(s: ReadingState, id: string): ReadingState {
  return { ...s, shown: add(s.shown, id), opened: add(s.opened, id) };
}

// Deux paires exclusives (intéressant / pas intéressant, facile / dur) ; « saved » est indépendant.
const OPPOSITE: Partial<Record<FeedbackType, FeedbackType>> = {
  interesting: "not_interesting",
  not_interesting: "interesting",
  too_easy: "too_hard",
  too_hard: "too_easy",
};

/** Bascule un feedback. Renvoie le nouvel état, ce qui a été ajouté et ce qui a été retiré. */
export function toggleFeedback(
  s: ReadingState,
  id: string,
  type: FeedbackType,
): { state: ReadingState; added: FeedbackType | null; removed: FeedbackType[] } {
  const current = s.feedback[id] ?? [];
  if (current.includes(type)) {
    const next = current.filter((t) => t !== type);
    return { state: { ...s, feedback: { ...s.feedback, [id]: next } }, added: null, removed: [type] };
  }
  const opposite = OPPOSITE[type];
  const removed = opposite && current.includes(opposite) ? [opposite] : [];
  const next = [...current.filter((t) => t !== opposite), type];
  return { state: { ...s, feedback: { ...s.feedback, [id]: next } }, added: type, removed };
}

/** Récapitulatif de fin d'édition : lus, ignorés, sauvegardés. */
export function summarize(cards: Pick<EditionCard, "arxiv_id">[], s: ReadingState) {
  const ids = cards.map((c) => c.arxiv_id);
  const read = ids.filter((id) => s.opened.includes(id)).length;
  const skipped = ids.filter((id) => s.shown.includes(id) && !s.opened.includes(id)).length;
  const saved = ids.filter((id) => (s.feedback[id] ?? []).includes("saved")).length;
  return { total: ids.length, read, skipped, saved };
}

const escapeHtml = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

export type HtmlColors = { text: string; background: string; muted: string };

/**
 * Page HTML qui affiche un texte contenant du LaTeX ($...$ et $$...$$) avec KaTeX.
 * Le texte vient d'un modèle : il est échappé, jamais inséré comme HTML.
 * La page annonce sa hauteur à l'app (WebView sur téléphone, iframe sur le web).
 */
export function buildMathHtml(text: string, colors: HtmlColors, fontSize = 17): string {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => `<p>${escapeHtml(p.trim())}</p>`)
    .join("");
  return `<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<style>
  html, body { margin: 0; padding: 0; background: ${colors.background}; }
  body { color: ${colors.text}; font: ${fontSize}px/1.6 Georgia, "Times New Roman", serif; overflow: hidden;
         -webkit-text-size-adjust: 100%; word-wrap: break-word; }
  p { margin: 0 0 0.9em 0; } p:last-child { margin-bottom: 0; }
  .katex-display { overflow-x: auto; overflow-y: hidden; padding: 2px 0; }
  .katex-error { color: ${colors.muted}; }
</style></head><body><div id="c">${paragraphs}</div>
<script>
  function send() {
    var h = Math.ceil(document.getElementById("c").getBoundingClientRect().height);
    if (window.ReactNativeWebView) window.ReactNativeWebView.postMessage(String(h));
    else if (window.parent !== window) window.parent.postMessage({ mathHeight: h }, "*");
  }
  function render() {
    try {
      renderMathInElement(document.getElementById("c"), {
        delimiters: [{ left: "$$", right: "$$", display: true }, { left: "$", right: "$", display: false }],
        throwOnError: false,
      });
    } catch (e) {}
    send();
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(send);
  }
  window.addEventListener("resize", send);
  send();
</script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js" onload="render()" onerror="send()"></script>
</body></html>`;
}

export const hasMath = (text: string) => text.includes("$");

/** Ligne de paper_figures telle que la base la renvoie. */
export type FigureDbRow = {
  paper_id: string;
  label: string;
  position: number;
  caption: string;
  roles: ("card" | "detail")[];
  what_to_look_at: string | null;
  sources: string[];
  storage_paths: string[];
  stored: boolean;
};

/**
 * Images à afficher pour une figure : la copie du stockage (adresses signées) si elle existe, sinon
 * les adresses d'origine sur arXiv. La clé de cache ne dépend pas de la signature, qui change.
 */
export function figureImages(row: FigureDbRow, signed: Record<string, string>): FigureImage[] {
  if (row.stored && row.storage_paths.length) {
    return row.storage_paths.filter((p) => signed[p]).map((p) => ({ uri: signed[p], cacheKey: `figures/${p}` }));
  }
  return row.sources.filter((u) => /^https?:\/\//.test(u)).map((u) => ({ uri: u, cacheKey: u }));
}

/** La figure de la carte (une au plus) et celles de la vue profondeur, dans l'ordre choisi par le modèle. */
export function figuresFor(
  figures: PaperFigure[],
  order: { label: string }[] = [],
): { card: PaperFigure | null; detail: PaperFigure[] } {
  const usable = figures.filter((f) => f.images.length);
  const rank = (f: PaperFigure) => {
    const i = order.findIndex((o) => o.label === f.label);
    return i < 0 ? 1000 + f.position : i;
  };
  return {
    card: usable.find((f) => f.roles.includes("card")) ?? null,
    detail: usable.filter((f) => f.roles.includes("detail")).sort((a, b) => rank(a) - rank(b)),
  };
}

// ---------- V2 : carnet ----------

/** « superconductivity, To Read ,  » -> ["superconductivity", "to read"] */
export function parseTags(text: string): string[] {
  const out: string[] = [];
  for (const raw of text.split(",")) {
    const t = raw.trim().toLowerCase().replace(/\s+/g, " ");
    if (t && !out.includes(t)) out.push(t);
  }
  return out;
}

export function allTags(entries: Pick<NotebookEntry, "tags">[]): string[] {
  return [...new Set(entries.flatMap((e) => e.tags))].sort();
}

/** Recherche sur le téléphone (donc aussi hors ligne) : tous les mots doivent apparaître quelque part. */
export function filterNotebook(entries: NotebookEntry[], query: string, tag: string | null): NotebookEntry[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return entries.filter((e) => {
    if (tag && !e.tags.includes(tag)) return false;
    if (!words.length) return true;
    const text = [e.title, e.plain_title ?? "", e.finding ?? "", e.note, e.tags.join(" "), e.authors.join(" "), e.paper_id]
      .join(" ")
      .toLowerCase();
    return words.every((w) => text.includes(w));
  });
}

/** Les identifiants arXiv commencent par l'année et le mois : « 2611.01234 » -> 2026. */
export function arxivYear(id: string): string {
  const m = /^(\d{2})\d{2}\./.exec(id);
  return m ? `20${m[1]}` : "";
}

export function toMarkdown(entries: NotebookEntry[]): string {
  const blocks = entries.map((e) => {
    const lines = [`## ${e.title}`, "", `${e.authors.join(", ")} — [arXiv:${e.paper_id}](https://arxiv.org/abs/${e.paper_id})`];
    if (e.plain_title) lines.push("", `**In plain words:** ${e.plain_title}`);
    if (e.finding) lines.push("", e.finding);
    if (e.tags.length) lines.push("", `Tags: ${e.tags.join(", ")}`);
    if (e.note.trim()) lines.push("", "### Notes", "", e.note.trim());
    lines.push("", `Saved on ${e.saved_at.slice(0, 10)}`);
    return lines.join("\n");
  });
  return `# Notebook\n\n${blocks.join("\n\n---\n\n")}\n`;
}

const STOP = new Set(["a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "from", "at", "by"]);
const ascii = (s: string) => s.normalize("NFD").replace(/[^a-zA-Z]/g, "").toLowerCase();

/** Clé BibTeX : nom du premier auteur, année, premier mot significatif du titre. */
export function bibKey(e: Pick<NotebookEntry, "paper_id" | "title" | "authors">): string {
  const last = ascii((e.authors[0] ?? "").trim().split(/\s+/).pop() ?? "") || "arxiv";
  const word = e.title.split(/\s+/).map(ascii).find((w) => w && !STOP.has(w)) ?? "";
  return `${last}${arxivYear(e.paper_id)}${word}`;
}

export function toBibtex(entries: NotebookEntry[]): string {
  const used = new Map<string, number>();
  return entries
    .map((e) => {
      const base = bibKey(e);
      const n = used.get(base) ?? 0;
      used.set(base, n + 1);
      const key = n ? `${base}${String.fromCharCode(97 + n)}` : base; // doublon : suffixe b, c…
      const fields = [
        `  title = {{${e.title}}}`,
        `  author = {${e.authors.join(" and ")}}`,
        `  year = {${arxivYear(e.paper_id)}}`,
        `  eprint = {${e.paper_id}}`,
        "  archivePrefix = {arXiv}",
        `  primaryClass = {${e.primary_category || e.categories[0] || ""}}`,
        `  url = {https://arxiv.org/abs/${e.paper_id}}`,
      ];
      return `@misc{${key},\n${fields.join(",\n")}\n}`;
    })
    .join("\n\n")
    .concat("\n");
}

// ---------- V2 : statistiques et bilan du lundi ----------

export const percent = (rate: number | null) => (rate === null ? "–" : `${Math.round(rate * 100)}%`);

/** « 2026-11-09 » -> « 9 Nov » */
export function shortDate(iso: string): string {
  const [, m, d] = iso.split("-").map(Number);
  return `${d} ${["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1]}`;
}

export function isMonday(iso: string): boolean {
  return new Date(`${iso}T12:00:00Z`).getUTCDay() === 1;
}

/** Le bilan n'est montré que le lundi, et seulement s'il y a eu quelque chose à lire la semaine passée. */
export function summaryFor(date: string, summary: WeekSummary | null): WeekSummary | null {
  return summary && isMonday(date) && summary.shown > 0 ? summary : null;
}

// ---------- V2 : profil ----------

export const WEIGHT_MIN = 0.2;
export const WEIGHT_MAX = 2.0;
export const SIZE_MIN = 3;
export const SIZE_MAX = 12;

/** Un cran de 0,1 sur la force du poids ; un mot-clé négatif garde son signe. */
export function stepWeight(weight: number, direction: 1 | -1): number {
  const size = Math.abs(weight) + 0.1 * direction;
  const clamped = Math.max(WEIGHT_MIN, Math.min(WEIGHT_MAX, Math.round(size * 10) / 10));
  return weight < 0 ? -clamped : clamped;
}

/** « 07:30 » + 30 min -> « 08:00 », borné entre deux heures. */
export function shiftTime(time: string, minutes: number, min: string, max: string): string {
  const [h, m] = time.split(":").map(Number);
  const lo = Number(min.slice(0, 2)) * 60 + Number(min.slice(3));
  const hi = Number(max.slice(0, 2)) * 60 + Number(max.slice(3));
  const t = Math.max(lo, Math.min(hi, h * 60 + m + minutes));
  return `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
}

export const weightId = (w: Pick<Weight, "kind" | "key">) => `${w.kind}:${w.key}`;

type ManualChange = { source: "manual"; kind: string; key: string; old_value: string | null; new_value: string; reason: string };

/**
 * Ce qu'il faut écrire en base quand le profil est modifié à la main. Un poids modifié déplace aussi
 * sa valeur de repos : l'apprentissage repart de la valeur saisie.
 */
export function profileDiff(
  before: { weights: Weight[]; levels: Level[] },
  after: { weights: Weight[]; levels: Level[] },
): { weights: Weight[]; removed: Weight[]; levels: Level[]; changes: ManualChange[] } {
  const old = new Map(before.weights.map((w) => [weightId(w), w]));
  const kept = new Set(after.weights.map(weightId));
  const changes: ManualChange[] = [];
  const weights: Weight[] = [];
  const log = (kind: string, key: string, a: string | null, b: string, reason: string) =>
    changes.push({ source: "manual", kind, key, old_value: a, new_value: b, reason });
  for (const w of after.weights) {
    const o = old.get(weightId(w));
    if (!o) {
      weights.push({ ...w, baseline: w.weight });
      log(w.kind, w.key, null, w.weight.toFixed(3), "added by hand");
    } else if (o.weight !== w.weight) {
      weights.push({ ...w, baseline: w.weight });
      log(w.kind, w.key, o.weight.toFixed(3), w.weight.toFixed(3), "set by hand");
    } else if (o.locked !== w.locked) {
      weights.push(w);
    }
  }
  const removed = before.weights.filter((w) => !kept.has(weightId(w)));
  for (const w of removed) log(w.kind, w.key, w.weight.toFixed(3), "removed", "removed by hand");
  const oldLevels = new Map(before.levels.map((l) => [l.category, l]));
  const levels: Level[] = [];
  for (const l of after.levels) {
    const o = oldLevels.get(l.category);
    const was = o?.level ?? "intermediate";
    if (was !== l.level) {
      levels.push({ ...l, drift: 0 });
      log("level", l.category, was, l.level, "set by hand");
    } else if ((o?.locked ?? false) !== l.locked) {
      levels.push(l);
    }
  }
  return { weights, removed, levels, changes };
}

/** Le dernier changement journalisé de chaque poids ou niveau (les changements arrivent du plus récent au plus ancien). */
export function lastChanges(changes: ProfileChange[]): Record<string, ProfileChange> {
  const out: Record<string, ProfileChange> = {};
  for (const c of changes) out[`${c.kind}:${c.key}`] ??= c;
  return out;
}

export function describeChange(c: ProfileChange | undefined): string {
  if (!c) return "";
  const move = c.old_value ? `${c.old_value} → ${c.new_value}` : c.new_value;
  return `${shortDate(c.changed_at.slice(0, 10))}: ${move}${c.reason ? ` · ${c.reason}` : ""}`;
}

export const DEFAULT_SETTINGS: Required<AppSettings> = {
  edition_size: 8,
  morning_time: "07:30",
  evening_time: "20:00",
  timezone: "Europe/Zurich",
};

// ---------- widget d'écran d'accueil ----------

/** Série et lectures récentes. `days` : une ligne par édition, dans n'importe quel ordre.
 * Une édition est faite si elle est terminée ou si toutes ses cartes ont été vues.
 * La dernière édition parue, pas encore faite, ne casse pas la série : elle est « en cours ».
 * L'état local (`local`) complète la base : il est à jour avant que la file d'envoi soit vidée. */
export function widgetData(days: WidgetDay[], local?: ReadingState | null): WidgetData {
  const sorted = [...days].sort((a, b) => b.date.localeCompare(a.date)).map((d) => {
    if (!local || local.date !== d.date) return d;
    const allSeen = d.size > 0 && local.shown.length >= d.size;
    return { ...d, read: Math.max(d.read, local.opened.length), done: d.done || local.completed || allSeen };
  });
  const today = sorted[0] ?? null;
  let streak = 0;
  for (const [i, d] of sorted.entries()) {
    if (d.done) streak += 1;
    else if (i > 0) break;
  }
  return { streak, today, days: sorted.slice(0, 7).reverse() };
}

/** Initiale du jour de la semaine d'une date AAAA-MM-JJ (en anglais, comme l'app). */
export function weekdayInitial(iso: string): string {
  return "SMTWTFS"[new Date(`${iso}T12:00:00Z`).getUTCDay()];
}

// ---------- V2, étape 4 : concepts et questions ----------

/** Un QCM est juste si l'option choisie est la bonne réponse (le serveur a ramené la réponse au texte d'une option). */
export const isRightOption = (q: Pick<QuestionRow, "answer">, option: string) => option === q.answer;

/** Dernière réponse donnée à chaque question, par identifiant. */
export function lastAttempts(attempts: Attempt[]): Record<number, Attempt> {
  const out: Record<number, Attempt> = {};
  for (const a of [...attempts].sort((x, y) => (x.created_at < y.created_at ? -1 : x.created_at > y.created_at ? 1 : 0))) {
    out[a.question_id] = a;
  }
  return out;
}

/** Fiches concepts qui contiennent tous les mots cherchés (nom, identifiant, définitions), par ordre alphabétique. */
export function filterConcepts(cards: ConceptCard[], query: string): ConceptCard[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return cards
    .filter((c) => {
      const hay = [c.name, c.id, c.simple_definition, c.expert_definition].join(" ").toLowerCase();
      return words.every((w) => hay.includes(w));
    })
    .sort((a, b) => a.name.localeCompare(b.name, "en", { sensitivity: "base" }));
}

/** Nom affiché d'un concept lié ; à défaut (fiche fusionnée entre-temps), son identifiant. */
export function conceptName(cards: Pick<ConceptCard, "id" | "name">[], id: string): string {
  return cards.find((c) => c.id === id)?.name ?? id;
}

/** « 3/4 » questions réussies du premier coup, ou « – » si aucune réponse. */
export const questionsLine = (answered = 0, correct = 0) => (answered ? `${correct}/${answered}` : "–");

/**
 * Options d'un QCM dans un ordre mélangé, toujours le même pour une question donnée : le modèle
 * place souvent la bonne réponse en premier.
 */
export function shuffledOptions(options: string[], seed: number): string[] {
  let s = (Math.abs(Math.trunc(seed)) * 2654435761 + 1) >>> 0;
  const next = () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 2 ** 32;
  };
  const out = [...options];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(next() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}
