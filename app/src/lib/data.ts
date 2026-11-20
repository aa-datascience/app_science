// Accès aux données : réseau d'abord, cache du téléphone en secours ; écritures mises en file d'attente.

import AsyncStorage from "@react-native-async-storage/async-storage";
import { FunctionsHttpError } from "@supabase/supabase-js";

import { supabase } from "./supabase";
import { type FigureDbRow, figureImages, profileDiff } from "./logic";
import type {
  AppSettings,
  Attempt,
  ConceptCard,
  DetailRow,
  EditionCard,
  Learning,
  Level,
  NotebookEntry,
  OutboxItem,
  PaperFigure,
  ProfileChange,
  ProfileData,
  QuestionRow,
  ReadingState,
  Stats,
  WeekSummary,
  Weight,
  WidgetDay,
} from "./types";

const K = {
  edition: "edition:last",
  state: "state:last",
  outbox: "outbox",
  detail: (id: string) => `detail:${id}`,
  figures: (id: string) => `figures:${id}`,
  notebook: "notebook",
  stats: (weeks: number) => `stats:${weeks}`,
  summary: (date: string) => `summary:${date}`,
  profile: "profile",
  widget: "widget:days",
  learning: (id: string) => `learning:${id}`,
  concepts: "concepts",
};

async function read<T>(key: string): Promise<T | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

const write = (key: string, value: unknown) => AsyncStorage.setItem(key, JSON.stringify(value)).catch(() => {});

// ---------- édition du jour ----------

export async function loadEdition(): Promise<{ cards: EditionCard[]; fromCache: boolean; error?: string }> {
  const { data, error } = await supabase.from("edition_today").select("*").order("position");
  if (!error && data) {
    await write(K.edition, data);
    return { cards: data as EditionCard[], fromCache: false };
  }
  const cached = await read<EditionCard[]>(K.edition);
  return { cards: cached ?? [], fromCache: true, error: error?.message };
}

export const loadState = () => read<ReadingState>(K.state);
export const saveState = (s: ReadingState) => write(K.state, s);

// ---------- figures ----------

const SIGNED_FOR_SECONDS = 60 * 60 * 24 * 30;

/**
 * Figures choisies (carte ou vue profondeur) des articles donnés, par article.
 * Réseau d'abord ; hors ligne, ce qui a été vu la dernière fois (les images sont en cache).
 */
export async function loadFigures(paperIds: string[]): Promise<Record<string, PaperFigure[]>> {
  const out: Record<string, PaperFigure[]> = {};
  if (!paperIds.length) return out;
  const { data, error } = await supabase
    .from("paper_figures")
    .select("paper_id,label,position,caption,roles,what_to_look_at,sources,storage_paths,stored")
    .in("paper_id", paperIds)
    .neq("roles", "{}")
    .order("position");
  if (error || !data) {
    for (const id of paperIds) out[id] = (await read<PaperFigure[]>(K.figures(id))) ?? [];
    return out;
  }
  const rows = data as FigureDbRow[];
  const paths = rows.flatMap((r) => (r.stored ? r.storage_paths : []));
  const signed: Record<string, string> = {};
  if (paths.length) {
    const res = await supabase.storage.from("figures").createSignedUrls(paths, SIGNED_FOR_SECONDS);
    for (const item of res.data ?? []) if (item.path && item.signedUrl) signed[item.path] = item.signedUrl;
  }
  for (const id of paperIds) out[id] = [];
  for (const r of rows) {
    out[r.paper_id]?.push({
      paper_id: r.paper_id,
      label: r.label,
      position: r.position,
      caption: r.caption,
      roles: r.roles,
      what_to_look_at: r.what_to_look_at,
      images: figureImages(r, signed),
    });
  }
  await Promise.all(paperIds.map((id) => write(K.figures(id), out[id])));
  return out;
}

// ---------- détail d'un article ----------

export type DetailResult =
  | { ok: true; detail: DetailRow }
  | { ok: false; reason: "budget" | "offline" | "error"; message?: string };

/**
 * Détail d'un article : cache du téléphone, puis base, puis génération par l'Edge Function
 * open-paper (première ouverture : quelques dizaines de secondes).
 */
export async function loadDetail(arxivId: string): Promise<DetailResult> {
  const cached = await read<DetailRow>(K.detail(arxivId));
  if (cached) return { ok: true, detail: cached };
  return generateDetail(arxivId, false);
}

/** Refait le détail d'un article déjà ouvert (bouton « Regenerate », appel payant). */
export const regenerateDetail = (arxivId: string) => generateDetail(arxivId, true);

async function generateDetail(arxivId: string, regenerate: boolean): Promise<DetailResult> {
  if (regenerate) return invokeOpenPaper(arxivId, true);

  // Déjà généré (par une ouverture précédente, sur cet appareil ou un autre) : simple lecture en base.
  const stored = await supabase.from("details").select("*").eq("paper_id", arxivId).maybeSingle();
  if (stored.data) {
    await write(K.detail(arxivId), stored.data);
    return { ok: true, detail: stored.data as DetailRow };
  }

  return invokeOpenPaper(arxivId, false);
}

async function invokeOpenPaper(arxivId: string, regenerate: boolean): Promise<DetailResult> {
  const body = regenerate ? { arxiv_id: arxivId, regenerate: true } : { arxiv_id: arxivId };
  const { data, error } = await supabase.functions.invoke("open-paper", { body });
  if (!error && data?.detail) {
    await write(K.detail(arxivId), data.detail);
    return { ok: true, detail: data.detail as DetailRow };
  }
  if (error instanceof FunctionsHttpError) {
    const status = (error.context as Response | undefined)?.status;
    if (status === 402) return { ok: false, reason: "budget" };
    return { ok: false, reason: "error", message: `HTTP ${status ?? "?"}` };
  }
  return { ok: false, reason: "offline", message: error?.message };
}

// ---------- écritures : feedback, événements de lecture, fin d'édition ----------

async function send(item: OutboxItem): Promise<boolean> {
  if (item.kind === "feedback") {
    return !(await supabase.from("feedback").insert(item.row)).error;
  }
  if (item.kind === "unfeedback") {
    return !(await supabase.from("feedback").delete().eq("paper_id", item.paper_id).eq("type", item.type)).error;
  }
  if (item.kind === "event") {
    return !(await supabase.from("reading_events").insert(item.row)).error;
  }
  if (item.kind === "notebook_add") {
    // Une entrée déjà là (note, tags) n'est pas écrasée.
    const row = { paper_id: item.paper_id, saved_at: item.at };
    return !(await supabase.from("notebook").upsert(row, { onConflict: "paper_id", ignoreDuplicates: true })).error;
  }
  if (item.kind === "notebook_remove") {
    return !(await supabase.from("notebook").delete().eq("paper_id", item.paper_id)).error;
  }
  if (item.kind === "attempt") {
    return !(await supabase.from("question_attempts").insert(item.row)).error;
  }
  if (item.kind === "notebook_update") {
    const row = { note: item.note, tags: item.tags, updated_at: item.at };
    return !(await supabase.from("notebook").update(row).eq("paper_id", item.paper_id)).error;
  }
  return !(await supabase.from("editions").update({ completed_at: item.at }).eq("date", item.date)).error;
}

let flushing: Promise<void> | null = null;

/** Envoie ce qui attend, dans l'ordre ; s'arrête au premier échec et réessaiera plus tard. */
export function flushOutbox(): Promise<void> {
  flushing ??= (async () => {
    try {
      let queue = (await read<OutboxItem[]>(K.outbox)) ?? [];
      while (queue.length) {
        if (!(await send(queue[0]))) break;
        // Relit la file : d'autres écritures ont pu s'ajouter pendant l'envoi.
        queue = ((await read<OutboxItem[]>(K.outbox)) ?? []).slice(1);
        await write(K.outbox, queue);
      }
    } finally {
      flushing = null;
    }
  })();
  return flushing;
}

let enqueueing: Promise<void> = Promise.resolve();

/** Ajoute une écriture à la file (jamais perdue hors ligne), puis tente l'envoi. */
export function enqueue(item: OutboxItem): Promise<void> {
  enqueueing = enqueueing.then(async () => {
    if (flushing) await flushing;
    const queue = (await read<OutboxItem[]>(K.outbox)) ?? [];
    await write(K.outbox, [...queue, item]);
  });
  return enqueueing.then(() => void flushOutbox());
}

// ---------- V2 : carnet ----------

const NOTEBOOK_COLUMNS = "paper_id,note,tags,saved_at,title,authors,categories,primary_category,plain_title,finding";

/** Tout le carnet, le plus récent d'abord. Les écritures en attente partent avant la lecture. */
export async function loadNotebook(): Promise<{ entries: NotebookEntry[]; fromCache: boolean }> {
  await flushOutbox();
  const { data, error } = await supabase.from("notebook_entries").select(NOTEBOOK_COLUMNS).order("saved_at", { ascending: false });
  if (!error && data) {
    await write(K.notebook, data);
    return { entries: data as NotebookEntry[], fromCache: false };
  }
  return { entries: (await read<NotebookEntry[]>(K.notebook)) ?? [], fromCache: true };
}

export const cachedNotebook = async () => (await read<NotebookEntry[]>(K.notebook)) ?? [];

/** Met à jour la copie du téléphone tout de suite ; l'écriture en base passe par la file d'attente. */
export async function patchCachedNotebook(change: (entries: NotebookEntry[]) => NotebookEntry[]): Promise<void> {
  await write(K.notebook, change(await cachedNotebook()));
}

// ---------- V2 : statistiques ----------

export async function loadStats(weeks: number): Promise<{ stats: Stats | null; fromCache: boolean }> {
  await flushOutbox();
  const { data, error } = await supabase.rpc("get_stats", { weeks });
  if (!error && data) {
    await write(K.stats(weeks), data);
    return { stats: data as Stats, fromCache: false };
  }
  return { stats: await read<Stats>(K.stats(weeks)), fromCache: true };
}

/** Bilan de la semaine passée, pour l'édition de cette date (gardé sur le téléphone pour le hors-ligne). */
export async function loadWeekSummary(date: string): Promise<WeekSummary | null> {
  const { data, error } = await supabase.rpc("last_week_summary");
  if (!error && data) {
    await write(K.summary(date), data);
    return data as WeekSummary;
  }
  return read<WeekSummary>(K.summary(date));
}

// ---------- V2 : profil ----------

export async function loadProfile(): Promise<{ profile: ProfileData | null; fromCache: boolean }> {
  const [prof, weights, levels, changes] = await Promise.all([
    supabase.from("profile").select("settings").eq("id", 1).maybeSingle(),
    supabase.from("profile_weights").select("kind,key,weight,baseline,locked").order("key"),
    supabase.from("profile_levels").select("category,level,drift,locked").order("category"),
    supabase
      .from("profile_changes")
      .select("kind,key,changed_at,source,old_value,new_value,reason")
      .order("changed_at", { ascending: false })
      .limit(300),
  ]);
  if (prof.error || weights.error || levels.error || changes.error) {
    return { profile: await read<ProfileData>(K.profile), fromCache: true };
  }
  const profile: ProfileData = {
    settings: (prof.data?.settings ?? {}) as AppSettings,
    weights: weights.data as Weight[],
    levels: levels.data as Level[],
    changes: changes.data as ProfileChange[],
  };
  await write(K.profile, profile);
  return { profile, fromCache: false };
}

/** Écrit les modifications faites à la main. Renvoie un message d'erreur, ou null si tout est écrit. */
export async function saveProfile(
  before: ProfileData,
  after: { settings: AppSettings; weights: Weight[]; levels: Level[] },
): Promise<string | null> {
  const diff = profileDiff(before, after);
  const now = new Date().toISOString();
  const steps: PromiseLike<{ error: { message: string } | null }>[] = [];
  if (JSON.stringify(before.settings) !== JSON.stringify(after.settings)) {
    steps.push(supabase.from("profile").update({ settings: after.settings, updated_at: now }).eq("id", 1));
  }
  if (diff.weights.length) {
    steps.push(supabase.from("profile_weights").upsert(diff.weights.map((w) => ({ ...w, updated_at: now })), { onConflict: "kind,key" }));
  }
  for (const w of diff.removed) {
    steps.push(supabase.from("profile_weights").delete().eq("kind", w.kind).eq("key", w.key));
  }
  if (diff.levels.length) {
    steps.push(supabase.from("profile_levels").upsert(diff.levels.map((l) => ({ ...l, updated_at: now })), { onConflict: "category" }));
  }
  if (diff.changes.length) steps.push(supabase.from("profile_changes").insert(diff.changes));
  for (const step of steps) {
    const { error } = await step;
    if (error) return error.message;
  }
  return null;
}

// ---------- widget d'écran d'accueil ----------

/** Les 30 dernières éditions : taille, articles lus (vue profondeur ouverte), faite ou non.
 * Faite : terminée (écran de fin atteint) ou toutes ses cartes vues. */
export async function loadWidgetDays(): Promise<WidgetDay[]> {
  const eds = await supabase.from("editions").select("date,completed_at").order("date", { ascending: false }).limit(30);
  const dates = (eds.data ?? []).map((e) => e.date as string);
  if (!eds.error && dates.length) {
    const log = await supabase.from("reading_log").select("edition_date,read,shown").gte("edition_date", dates[dates.length - 1]);
    if (!log.error && log.data) {
      const days = (eds.data ?? []).map((e) => {
        const rows = log.data.filter((r) => r.edition_date === e.date);
        return { date: e.date as string, size: rows.length, read: rows.filter((r) => r.read).length, done: Boolean(e.completed_at) || (rows.length > 0 && rows.every((r) => r.shown)) };
      });
      await write(K.widget, days);
      return days;
    }
  }
  return (await read<WidgetDay[]>(K.widget)) ?? [];
}

// ---------- V2, étape 4 : concepts et questions ----------

/**
 * Concepts et questions d'un article, avec les réponses déjà données. Réseau d'abord, cache en secours.
 * Les réponses encore dans la file d'attente sont ajoutées à celles lues en base.
 */
export async function loadLearning(paperId: string): Promise<Learning | null> {
  const cached = await read<Learning>(K.learning(paperId));
  const [pc, qs] = await Promise.all([
    supabase.from("paper_concepts").select("position, concepts(id, name)").eq("paper_id", paperId).order("position"),
    supabase.from("questions").select("id,paper_id,position,kind,prompt,options,answer,explanation,quote")
      .eq("paper_id", paperId).is("archived_at", null).order("position"),
  ]);
  if (pc.error || qs.error) return cached;
  const questions = (qs.data ?? []) as QuestionRow[];
  const ids = questions.map((q) => q.id);
  const at = ids.length
    ? await supabase.from("question_attempts").select("question_id,answer,correct,created_at").in("question_id", ids)
    : { data: [], error: null };
  if (at.error) return cached;
  const pending = ((await read<OutboxItem[]>(K.outbox)) ?? [])
    .flatMap((i) => (i.kind === "attempt" && ids.includes(i.row.question_id) ? [i.row] : []));
  const learning: Learning = {
    concepts: (pc.data ?? []).flatMap((r) => {
      const c = r.concepts as unknown as { id: string; name: string } | null;
      return c ? [{ id: c.id, name: c.name }] : [];
    }),
    questions,
    attempts: [...((at.data ?? []) as Attempt[]), ...pending],
  };
  await write(K.learning(paperId), learning);
  return learning;
}

/** Enregistre une réponse : tout de suite sur le téléphone, en base par la file d'attente. */
export async function recordAttempt(paperId: string, attempt: Attempt): Promise<void> {
  const cached = await read<Learning>(K.learning(paperId));
  if (cached) await write(K.learning(paperId), { ...cached, attempts: [...cached.attempts, attempt] });
  await enqueue({ kind: "attempt", row: attempt });
}

/** Toutes les fiches concepts. Réseau d'abord ; hors ligne, la dernière liste vue. */
export async function loadConcepts(): Promise<{ concepts: ConceptCard[]; fromCache: boolean }> {
  const { data, error } = await supabase.from("concept_cards").select("*");
  if (!error && data) {
    await write(K.concepts, data);
    return { concepts: data as ConceptCard[], fromCache: false };
  }
  return { concepts: (await read<ConceptCard[]>(K.concepts)) ?? [], fromCache: true };
}

export const cachedConcepts = async () => (await read<ConceptCard[]>(K.concepts)) ?? [];

/** Fusionne `dup` dans `keep` (doublons). Renvoie un message d'erreur, ou null. En ligne seulement. */
export async function mergeConcepts(dup: string, keep: string): Promise<string | null> {
  const { error } = await supabase.rpc("merge_concepts", { dup, keep });
  return error ? error.message : null;
}

/** Nombre de concepts créés par les articles de cette édition (récapitulatif de fin) ; null hors ligne. */
export async function countNewConcepts(paperIds: string[]): Promise<number | null> {
  if (!paperIds.length) return 0;
  const { count, error } = await supabase.from("concepts").select("id", { count: "exact", head: true }).in("first_paper_id", paperIds);
  return error ? null : (count ?? 0);
}
