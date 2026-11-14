// Accès aux données : réseau d'abord, cache du téléphone en secours ; écritures mises en file d'attente.

import AsyncStorage from "@react-native-async-storage/async-storage";
import { FunctionsHttpError } from "@supabase/supabase-js";

import { supabase } from "./supabase";
import { type FigureDbRow, figureImages } from "./logic";
import type { DetailRow, EditionCard, OutboxItem, PaperFigure, ReadingState } from "./types";

const K = {
  edition: "edition:last",
  state: "state:last",
  outbox: "outbox",
  detail: (id: string) => `detail:${id}`,
  figures: (id: string) => `figures:${id}`,
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

  // Déjà généré (par une ouverture précédente, sur cet appareil ou un autre) : simple lecture en base.
  const stored = await supabase.from("details").select("*").eq("paper_id", arxivId).maybeSingle();
  if (stored.data) {
    await write(K.detail(arxivId), stored.data);
    return { ok: true, detail: stored.data as DetailRow };
  }

  const { data, error } = await supabase.functions.invoke("open-paper", { body: { arxiv_id: arxivId } });
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
