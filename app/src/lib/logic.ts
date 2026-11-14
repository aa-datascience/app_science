// Logique pure, sans dépendance à React Native : testée par `npm test` (node --test).

import type { EditionCard, FeedbackType, FigureImage, PaperFigure, ReadingState } from "./types.ts";

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
