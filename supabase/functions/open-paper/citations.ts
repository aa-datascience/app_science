// Vérification des citations sans appel au modèle.
// Portage à l'identique de pipeline/arxiv_digest/citations.py : toute modification doit être
// faite des deux côtés, et les deux sont testés sur pipeline/tests/fixtures/citation_cases.json.

export type Claim = { statement: string; quote: string };

export const MAX_FAILED_SHARE = 1 / 3; // au-delà, l'article est marqué « non vérifié »
export const MIN_QUOTE_CHARS = 20; // après normalisation

// Commandes LaTeX de pure mise en forme.
const FORMAT_CMD =
  /\\(?:mathrm|mathbf|mathit|mathcal|mathbb|mathsf|boldsymbol|bm|text|textrm|textit|textbf|emph|operatorname|left|right|big|Big|bigg|Bigg|displaystyle|rm|it|bf|quad|qquad|,|;|!|:| )(?![a-zA-Z])/g;

/** Ne garde que lettres et chiffres, en minuscules : « $T_{c}$ » et « T_c » donnent « tc ». */
export function normalize(s: string): string {
  return s
    .normalize("NFKC")
    .replace(FORMAT_CMD, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]/gu, "");
}

export function quoteFound(quote: string, normalizedText: string): boolean {
  const q = normalize(quote);
  return q.length >= MIN_QUOTE_CHARS && normalizedText.includes(q);
}

/** Retire les affirmations dont la citation est introuvable dans le texte. */
export function checkClaims(
  claims: Claim[],
  text: string,
): { kept: Claim[]; removed: Claim[]; status: "verified" | "unverified" } {
  const hay = normalize(text);
  const kept = claims.filter((c) => quoteFound(c.quote, hay));
  const removed = claims.filter((c) => !quoteFound(c.quote, hay));
  const ok = claims.length > 0 && removed.length <= claims.length * MAX_FAILED_SHARE;
  return { kept, removed, status: ok ? "verified" : "unverified" };
}
