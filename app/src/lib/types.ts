// Formes des données lues dans Supabase (voir supabase/migrations/).

export type Card = {
  plain_title: string;
  finding: string;
  why_it_matters: string;
  tags: string[];
  difficulty: number;
};

/** Une ligne de la vue edition_today : une carte de l'édition du jour. */
export type EditionCard = {
  date: string;
  status: string;
  completed_at: string | null;
  position: number;
  slot: "main" | "exploration";
  arxiv_id: string;
  title: string;
  authors: string[];
  categories: string[];
  card: Card;
  why: string | null;
  has_detail: boolean;
};

export type Claim = { statement: string; quote: string };

/** Une ligne de la table details : générée à la première ouverture, jamais régénérée. */
export type DetailRow = {
  paper_id: string;
  detail: {
    explanation_lay: string;
    explanation_expert: string;
    context: { before: string; change: string; limitations: string };
    claims: Claim[];
  };
  removed_claims: Claim[];
  verification_status: "verified" | "unverified";
  text_source: "html" | "latex" | "pdf" | "abstract";
  based_on_abstract: boolean;
  text_truncated: boolean;
  model: string;
};

export type FeedbackType = "interesting" | "not_interesting" | "too_easy" | "too_hard" | "saved";

/** Ce que l'utilisateur a fait de l'édition, gardé sur le téléphone. */
export type ReadingState = {
  date: string;
  shown: string[]; // cartes apparues à l'écran
  opened: string[]; // vues profondeur ouvertes
  feedback: Record<string, FeedbackType[]>;
  index: number; // dernière carte affichée
  completed: boolean;
};

/** Écriture en attente d'envoi (hors ligne, ou réseau en panne). */
export type OutboxItem =
  | { kind: "feedback"; row: { paper_id: string; type: FeedbackType; created_at: string } }
  | { kind: "unfeedback"; paper_id: string; type: FeedbackType }
  | {
      kind: "event";
      row: { paper_id: string | null; edition_date: string; event: string; section?: string; created_at: string };
    }
  | { kind: "complete"; date: string; at: string };
