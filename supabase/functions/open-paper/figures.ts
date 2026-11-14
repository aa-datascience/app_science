// Figures : liste donnée au modèle et validation de son choix.
// Portage à l'identique de figures_for_prompt et valid_labels (pipeline/arxiv_digest/figures.py) :
// les deux sont testés sur pipeline/tests/fixtures/figure_cases.json.

export type FigureRow = { label: string; caption: string };

export const CAPTION_CHARS_IN_PROMPT = 700;

/** La liste des figures telle que le prompt la reçoit. */
export function figuresForPrompt(figures: FigureRow[]): string {
  if (!figures.length) return "(no figures available)";
  return figures
    .map((f) => {
      const chars = Array.from(f.caption); // par caractère, comme Python
      const caption = chars.length <= CAPTION_CHARS_IN_PROMPT
        ? f.caption
        : chars.slice(0, CAPTION_CHARS_IN_PROMPT).join("") + "…";
      return `[${f.label}] ${caption}`;
    })
    .join("\n");
}

const stripEnds = (s: string, chars: string) => {
  let a = 0;
  let b = s.length;
  while (a < b && chars.includes(s[a])) a++;
  while (b > a && chars.includes(s[b - 1])) b--;
  return s.slice(a, b);
};

/** Ne garde que les labels qui existent dans la liste extraite, sans doublon, au plus `limit`. */
export function validLabels(chosen: string[], figures: FigureRow[], limit: number): string[] {
  const known = new Set(figures.map((f) => f.label));
  const out: string[] = [];
  for (const raw of chosen) {
    let label = (raw ?? "").trim();
    if (label.startsWith("Fig.")) label = label.slice(4);
    if (label.startsWith("Figure")) label = label.slice(6);
    label = stripEnds(label, " []");
    if (known.has(label) && !out.includes(label)) out.push(label);
  }
  return out.slice(0, limit);
}
