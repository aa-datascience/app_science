// Session Supabase et édition du jour, partagées par tous les écrans.

import type { Session } from "@supabase/supabase-js";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { AppState } from "react-native";

import { enqueue, flushOutbox, loadEdition, loadFigures, loadState, loadWeekSummary, saveState } from "./data";
import { emptyState, isMonday, markOpened, markShown, stateFor, summaryFor, toggleFeedback } from "./logic";
import { configureForeground, registerPush } from "./notifications";
import { supabase } from "./supabase";
import { updateWidget } from "../widget";
import type { EditionCard, FeedbackType, PaperFigure, ReadingState, WeekSummary } from "./types";

type Ctx = {
  session: Session | null;
  ready: boolean; // la session enregistrée a été relue
  cards: EditionCard[];
  figures: Record<string, PaperFigure[]>; // figures choisies, par article
  refreshFigures: (paperId: string) => Promise<void>; // après la génération d'un détail
  state: ReadingState;
  loading: boolean;
  fromCache: boolean;
  refresh: () => Promise<void>;
  summary: WeekSummary | null; // bilan de la semaine passée, le lundi seulement
  shown: (id: string, index: number) => void;
  viewed: (id: string, ms: number, date: string) => void; // temps passé sur une carte de l'édition `date`
  opened: (id: string) => void;
  feedback: (id: string, type: FeedbackType) => void;
  unsave: (id: string) => void; // retirer du carnet annule le Save
  complete: () => void;
};

const Context = createContext<Ctx | null>(null);

export function useApp(): Ctx {
  const ctx = useContext(Context);
  if (!ctx) throw new Error("useApp hors de AppProvider");
  return ctx;
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [ready, setReady] = useState(false);
  const [cards, setCards] = useState<EditionCard[]>([]);
  const [figures, setFigures] = useState<Record<string, PaperFigure[]>>({});
  const [state, setState] = useState<ReadingState>(emptyState(""));
  const [loading, setLoading] = useState(false);
  const [fromCache, setFromCache] = useState(false);
  const [summary, setSummary] = useState<WeekSummary | null>(null);
  const cardIds = useRef<string[]>([]);
  const stateRef = useRef(state);

  const update = useCallback((next: ReadingState) => {
    stateRef.current = next;
    setState(next);
    void saveState(next);
  }, []);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, s) => setSession(s));
    return () => data.subscription.unsubscribe();
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    const result = await loadEdition();
    const date = result.cards[0]?.date ?? "";
    const saved = stateFor(date, await loadState());
    // Une édition terminée sur un autre appareil l'est aussi ici.
    const completed = saved.completed || Boolean(result.cards[0]?.completed_at);
    const weekSummary = async () => (date && isMonday(date) ? summaryFor(date, await loadWeekSummary(date)) : null);
    // Nouvelle édition : le bilan du lundi est lu avant de l'afficher, pour qu'un écran de cartes
    // ouvert reparte de zéro avec le bon bilan (et pas celui de la veille).
    const newEdition = date !== stateRef.current.date;
    if (newEdition) setSummary(await weekSummary());
    setCards(result.cards);
    cardIds.current = result.cards.map((c) => c.arxiv_id);
    setFromCache(result.fromCache);
    update({ ...saved, completed });
    setLoading(false);
    void flushOutbox();
    if (!newEdition) setSummary(await weekSummary());
    setFigures(await loadFigures(result.cards.map((c) => c.arxiv_id)));
  }, [update]);

  const refreshFigures = useCallback(async (paperId: string) => {
    const fresh = await loadFigures([paperId]);
    setFigures((all) => ({ ...all, ...fresh }));
  }, []);

  const userId = session?.user.id;
  useEffect(() => {
    if (userId) void refresh();
    else setCards([]);
  }, [userId, refresh]);

  // Au retour au premier plan : relire l'édition. C'est là qu'on découvre qu'on est hors ligne
  // (ou revenu en ligne), et qu'une nouvelle édition est arrivée.
  useEffect(() => {
    if (!userId) return;
    const sub = AppState.addEventListener("change", (next) => {
      if (next === "active") void refresh();
    });
    return () => sub.remove();
  }, [userId, refresh]);

  // Notifications : à la connexion, on demande l'autorisation et on enregistre le jeton du téléphone.
  useEffect(() => {
    if (!userId) return;
    void configureForeground();
    void registerPush(true);
  }, [userId]);

  // Widget d'écran d'accueil : redessiné quand la lecture avance (édition lue ou terminée, nouvelle édition).
  useEffect(() => {
    if (userId && state.date) void updateWidget(stateRef.current);
  }, [userId, state.date, state.opened.length, state.completed]);

  const now = () => new Date().toISOString();

  const shown = useCallback(
    (id: string, index: number) => {
      const s = stateRef.current;
      const first = !s.shown.includes(id);
      update(markShown(s, id, index));
      if (first) void enqueue({ kind: "event", row: { paper_id: id, edition_date: s.date, event: "shown", created_at: now() } });
    },
    [update],
  );

  const viewed = useCallback((id: string, ms: number, date: string) => {
    // La date vient de l'écran : à l'arrivée d'une nouvelle édition, le temps de la dernière carte
    // de la veille est envoyé après le changement d'édition.
    if (!date) return;
    const row = { paper_id: id, edition_date: date, event: "viewed", duration_ms: Math.round(ms), created_at: now() };
    void enqueue({ kind: "event", row });
  }, []);

  const opened = useCallback(
    (id: string) => {
      const s = stateRef.current;
      if (!cardIds.current.includes(id)) return; // article rouvert depuis le carnet : hors de l'édition du jour
      const first = !s.opened.includes(id);
      update(markOpened(s, id));
      if (first) void enqueue({ kind: "event", row: { paper_id: id, edition_date: s.date, event: "opened", created_at: now() } });
    },
    [update],
  );

  const feedback = useCallback(
    (id: string, type: FeedbackType) => {
      const { state: next, added, removed } = toggleFeedback(stateRef.current, id, type);
      update(next);
      for (const t of removed) void enqueue({ kind: "unfeedback", paper_id: id, type: t });
      if (added) void enqueue({ kind: "feedback", row: { paper_id: id, type: added, created_at: now() } });
      // Save crée l'entrée du carnet ; l'annuler la retire.
      if (added === "saved") void enqueue({ kind: "notebook_add", paper_id: id, at: now() });
      if (removed.includes("saved")) void enqueue({ kind: "notebook_remove", paper_id: id });
    },
    [update],
  );

  const unsave = useCallback(
    (id: string) => {
      const s = stateRef.current;
      const given = s.feedback[id] ?? [];
      if (given.includes("saved")) update({ ...s, feedback: { ...s.feedback, [id]: given.filter((t) => t !== "saved") } });
      void enqueue({ kind: "unfeedback", paper_id: id, type: "saved" });
      void enqueue({ kind: "notebook_remove", paper_id: id });
    },
    [update],
  );

  const complete = useCallback(() => {
    const s = stateRef.current;
    if (s.completed || !s.date) return;
    update({ ...s, completed: true });
    void enqueue({ kind: "event", row: { paper_id: null, edition_date: s.date, event: "edition_completed", created_at: now() } });
    void enqueue({ kind: "complete", date: s.date, at: now() });
  }, [update]);

  return (
    <Context.Provider value={{
        session, ready, cards, figures, refreshFigures, state, loading, fromCache, refresh, summary, shown, viewed,
        opened, feedback, unsave, complete,
      }}>
      {children}
    </Context.Provider>
  );
}
