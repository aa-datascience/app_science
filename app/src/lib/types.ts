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

/** Une image de figure prête à afficher : adresse (signée ou d'origine) et clé de cache stable. */
export type FigureImage = { uri: string; cacheKey: string };

/** Une figure choisie pour la carte ou pour la vue profondeur (table paper_figures). */
export type PaperFigure = {
  paper_id: string;
  label: string;
  position: number;
  caption: string;
  roles: ("card" | "detail")[];
  what_to_look_at: string | null;
  images: FigureImage[];
};

/** Une ligne de la table details : générée à la première ouverture, jamais régénérée. */
export type DetailRow = {
  paper_id: string;
  detail: {
    explanation_lay: string;
    explanation_expert: string;
    context: { before: string; change: string; limitations: string };
    claims: Claim[];
    figures?: { label: string; what_to_look_at: string }[];
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
      row: {
        paper_id: string | null;
        edition_date: string;
        event: string;
        section?: string;
        duration_ms?: number; // événement « viewed » : temps passé sur la carte
        created_at: string;
      };
    }
  | { kind: "complete"; date: string; at: string }
  | { kind: "notebook_add"; paper_id: string; at: string }
  | { kind: "notebook_remove"; paper_id: string }
  | { kind: "notebook_update"; paper_id: string; note: string; tags: string[]; at: string };

// ---------- V2 : carnet, statistiques, profil ----------

/** Une ligne de la vue notebook_entries. */
export type NotebookEntry = {
  paper_id: string;
  note: string;
  tags: string[];
  saved_at: string;
  title: string;
  authors: string[];
  categories: string[];
  primary_category: string;
  plain_title: string | null;
  finding: string | null;
};

export type WeekStats = {
  week: string; // lundi de la semaine
  shown: number;
  read: number;
  skipped: number;
  saved: number;
  read_rate: number | null;
  editions_completed: number;
};

export type CategoryStats = { category: string; shown: number; read: number; read_rate: number | null };

/** Résultat de get_stats(weeks). */
export type Stats = { weeks: WeekStats[]; categories: CategoryStats[] };

/** Résultat de last_week_summary() : le bilan affiché en tête de l'édition du lundi. */
export type WeekSummary = {
  week: string;
  shown: number;
  read: number;
  skipped: number;
  saved: number;
  editions_completed: number;
  most_read_category: string | null;
  most_skipped_category: string | null;
};

export type Weight = { kind: "category" | "keyword" | "author"; key: string; weight: number; baseline: number; locked: boolean };
export type LevelName = "beginner" | "intermediate" | "expert";
export type Level = { category: string; level: LevelName; drift: number; locked: boolean };
export type ProfileChange = {
  kind: string;
  key: string;
  changed_at: string;
  source: string;
  old_value: string | null;
  new_value: string;
  reason: string | null;
};

/** profile.settings : réglages lus par le pipeline de nuit et par les notifications. */
export type AppSettings = { edition_size?: number; morning_time?: string; evening_time?: string; timezone?: string };

export type ProfileData = { settings: AppSettings; weights: Weight[]; levels: Level[]; changes: ProfileChange[] };

/** Widget d'écran d'accueil : une édition, avec ce qui en a été lu. */
export type WidgetDay = { date: string; size: number; read: number; done: boolean };
export type WidgetData = {
  streak: number; // éditions terminées d'affilée, sans compter celle du jour si elle est en cours
  today: WidgetDay | null; // dernière édition parue
  days: WidgetDay[]; // 7 dernières éditions, de la plus ancienne à la plus récente
};
