// Session Supabase et édition du jour, partagées par tous les écrans.

import type { Session } from "@supabase/supabase-js";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";

import { enqueue, flushOutbox, loadEdition, loadFigures, loadState, saveState } from "./data";
import { emptyState, markOpened, markShown, stateFor, toggleFeedback } from "./logic";
import { configureForeground, registerPush } from "./notifications";
import { supabase } from "./supabase";
import type { EditionCard, FeedbackType, PaperFigure, ReadingState } from "./types";

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
  shown: (id: string, index: number) => void;
  opened: (id: string) => void;
  feedback: (id: string, type: FeedbackType) => void;
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
    setCards(result.cards);
    setFromCache(result.fromCache);
    update({ ...saved, completed });
    setLoading(false);
    void flushOutbox();
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

  // Notifications : à la connexion, on demande l'autorisation et on enregistre le jeton du téléphone.
  useEffect(() => {
    if (!userId) return;
    void configureForeground();
    void registerPush(true);
  }, [userId]);

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

  const opened = useCallback(
    (id: string) => {
      const s = stateRef.current;
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
        session, ready, cards, figures, refreshFigures, state, loading, fromCache, refresh, shown, opened, feedback,
        complete,
      }}>
      {children}
    </Context.Provider>
  );
}
