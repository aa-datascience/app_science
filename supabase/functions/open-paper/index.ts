// Edge Function open-paper : génère le détail d'un article à sa première ouverture dans l'app.
//
//   POST /functions/v1/open-paper   { "arxiv_id": "2611.01234", "regenerate"?: true }   (session du propriétaire)
//   -> 200 { detail: <ligne de la table details>, cached: boolean }
//   -> 402 { error: "budget" }      plafond mensuel atteint
//   -> 404 { error: "not_found" }   l'article n'est dans aucune édition
//   -> 502 { error: "generation" }  le modèle n'a pas rendu de détail exploitable
//
// Même logique que `python -m arxiv_digest open` (pipeline/arxiv_digest/cli.py) :
// détail déjà en base -> renvoyé tel quel ; sinon un seul appel au modèle, puis vérification
// des citations sans modèle, puis stockage. `regenerate` (bouton de la vue profondeur, payant)
// refait le détail d'un article déjà ouvert : ses anciennes questions sont archivées, pas supprimées.
//
// V2, étape 4 : le même appel rend aussi 1 à 3 concepts et 2 ou 3 questions, contrôlés par
// learning.ts (portage de learning.py) et écrits dans leurs tables ; l'app ne les écrit jamais.
//
// Modèle, prix, plafond, prompts et schéma de sortie viennent de la table server_config,
// réécrite chaque nuit par le pipeline à partir de config.yaml et de prompts/.

import Anthropic from "npm:@anthropic-ai/sdk@^1.8.0";
import { createClient } from "npm:@supabase/supabase-js@2";

import { checkClaims, type Claim } from "./citations.ts";
import { figuresForPrompt, validLabels } from "./figures.ts";
import { checkQuestions, type ConceptEntry, type KnownConcept, knownForPrompt, MAX_KNOWN, type Question, resolveConcepts } from "./learning.ts";

type ServerConfig = {
  detail_model: string;
  effort: string;
  max_tokens: number;
  monthly_usd: number;
  prices: Record<string, number[]>; // [entrée, sortie, lecture de cache?] en USD par million de tokens
  assumed_detail_tokens: [number, number];
  levels: Record<string, string>;
  prompts: { system: string; detail: string };
  prompt_version: string;
  source_notes: Record<string, string>;
  detail_schema: Record<string, unknown>;
  max_known_concepts?: number;
};

// En-têtes CORS : inutiles pour l'app Android, nécessaires quand l'app tourne dans un navigateur.
// L'accès reste contrôlé par la session du propriétaire, pas par l'origine.
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

/** Date du jour à Zurich, AAAA-MM-JJ : même convention que le pipeline. */
const today = () => new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Zurich" }).format(new Date());

function cost(prices: number[] | undefined, inputTokens: number, outputTokens: number): number {
  if (!prices) return 0;
  return (inputTokens * prices[0] + outputTokens * prices[1]) / 1_000_000;
}

function render(template: string, values: Record<string, string>): string {
  let out = template;
  for (const [k, v] of Object.entries(values)) out = out.replaceAll(`{{${k}}}`, v);
  return out.trim();
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "method" }, 405);

  const url = Deno.env.get("SUPABASE_URL")!;
  // 1. Seul le propriétaire peut déclencher une génération (elle coûte de l'argent).
  const asUser = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } },
  });
  const { data: isOwner } = await asUser.rpc("is_owner");
  if (isOwner !== true) return json({ error: "forbidden" }, 403);

  const body = await req.json().catch(() => null);
  const arxivId = typeof body?.arxiv_id === "string" ? body.arxiv_id : "";
  const regenerate = body?.regenerate === true;
  if (!arxivId) return json({ error: "arxiv_id" }, 400);

  const db = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);

  // 2. Déjà généré : renvoyé tel quel, sauf régénération demandée.
  const existing = await db.from("details").select("*").eq("paper_id", arxivId).maybeSingle();
  if (existing.error) return json({ error: "database", message: existing.error.message }, 500);
  if (existing.data && !regenerate) return json({ detail: existing.data, cached: true });

  // 3. L'article doit faire partie d'une édition.
  const inEdition = await db.from("edition_items").select("paper_id").eq("paper_id", arxivId).limit(1);
  const paperRes = await db.from("papers").select("*").eq("arxiv_id", arxivId).maybeSingle();
  const paper = paperRes.data;
  if (!paper || !inEdition.data?.length) return json({ error: "not_found" }, 404);

  const cfgRes = await db.from("server_config").select("config").eq("id", 1).maybeSingle();
  const cfg = cfgRes.data?.config as ServerConfig | undefined;
  if (!cfg) return json({ error: "config", message: "server_config vide : lancer le pipeline de nuit" }, 500);
  const prices = cfg.prices[cfg.detail_model];

  // 4. Plafond mensuel : refus si le coût estimé de ce détail le ferait dépasser.
  const day = today();
  const monthStart = day.slice(0, 8) + "01";
  const usage = await db.from("api_usage").select("step, model, mode, cost_usd").gte("date", monthStart).order("id");
  if (usage.error) return json({ error: "database", message: usage.error.message }, 500);
  const spent = usage.data.reduce((sum, r) => sum + Number(r.cost_usd), 0);
  const textMode = paper.full_text ? (paper.text_mode ?? "full") : "full";
  const past = usage.data
    .filter((r) => r.step === "detail" && r.model === cfg.detail_model && (r.mode ?? "full") === textMode)
    .slice(-20)
    .map((r) => Number(r.cost_usd));
  const estimate = past.length
    ? past.reduce((a, b) => a + b, 0) / past.length
    : cost(prices, cfg.assumed_detail_tokens[0], cfg.assumed_detail_tokens[1]);
  if (spent + estimate > cfg.monthly_usd) return json({ error: "budget", spent, cap: cfg.monthly_usd }, 402);

  // Figures décrites la nuit par le pipeline : le modèle en choisit une à trois.
  const figRes = await db.from("paper_figures").select("label, caption, roles").eq("paper_id", arxivId).order("position");
  const figureRows: { label: string; caption: string; roles: string[] }[] = figRes.data ?? [];

  // Concepts déjà connus : le modèle réutilise leurs identifiants (150 au plus, même domaine d'abord).
  const conceptsRes = await db.from("concepts").select("id, name, primary_category, created_at");
  const known: KnownConcept[] = conceptsRes.error ? [] : conceptsRes.data ?? [];
  const learningReady = !conceptsRes.error; // tables de l'étape 4 présentes

  // 5. Texte stocké la nuit ; à défaut, le résumé (l'article est alors marqué « basé sur le résumé »).
  const text: string = paper.full_text ?? paper.abstract;
  const source: string = paper.full_text ? paper.text_source : "abstract";
  const truncated: boolean = paper.full_text ? paper.text_truncated : false;
  const authors: string[] = paper.authors ?? [];
  const prompt = render(cfg.prompts.detail, {
    source_note:
      cfg.source_notes[textMode === "sections" ? "sections" : source] + (truncated ? cfg.source_notes.truncated : ""),
    title: paper.title,
    authors: authors.slice(0, 12).join(", ") + (authors.length > 12 ? " et al." : ""),
    arxiv_id: paper.arxiv_id,
    categories: (paper.categories ?? []).join(", "),
    level: cfg.levels[paper.primary_category] ?? "intermediate",
    figures: figuresForPrompt(figureRows),
    known_concepts: knownForPrompt(known, paper.primary_category, cfg.max_known_concepts ?? MAX_KNOWN),
  });

  // 6. Un seul appel au modèle, sortie contrainte par le schéma du détail.
  const anthropic = new Anthropic(); // lit ANTHROPIC_API_KEY (secret de la fonction)
  let message: Anthropic.Message;
  try {
    message = await anthropic.messages.create({
      model: cfg.detail_model,
      max_tokens: cfg.max_tokens,
      system: cfg.prompts.system,
      messages: [{
        role: "user",
        content: [{ type: "text", text: `<paper>\n${text}\n</paper>` }, { type: "text", text: prompt }],
      }],
      output_config: {
        effort: cfg.effort as "low" | "medium" | "high",
        format: { type: "json_schema", schema: cfg.detail_schema },
      },
    });
  } catch (e) {
    if (e instanceof Anthropic.APIError) return json({ error: "generation", status: e.status, message: e.message }, 502);
    throw e;
  }

  // L'appel est payé quel que soit son résultat : on le journalise d'abord.
  const usd = cost(prices, message.usage.input_tokens, message.usage.output_tokens);
  await db.from("api_usage").insert({
    date: day,
    step: "detail",
    model: cfg.detail_model,
    batch: false,
    arxiv_id: arxivId,
    mode: textMode,
    label: regenerate ? "regenerate" : "",
    input_tokens: message.usage.input_tokens,
    output_tokens: message.usage.output_tokens,
    cost_usd: usd,
  });

  if (message.stop_reason === "refusal" || message.stop_reason === "max_tokens") {
    return json({ error: "generation", message: `stop_reason ${message.stop_reason}` }, 502);
  }
  const block = message.content.find((b) => b.type === "text");
  let detail: {
    explanation_lay: string;
    explanation_expert: string;
    context: Record<string, string>;
    claims: Claim[];
    figures?: { label: string; what_to_look_at: string }[];
    concepts?: ConceptEntry[];
    questions?: Partial<Question>[];
  };
  try {
    detail = JSON.parse(block && block.type === "text" ? block.text : "");
  } catch {
    return json({ error: "generation", message: "JSON invalide" }, 502);
  }
  if (!Array.isArray(detail?.claims)) return json({ error: "generation", message: "détail sans affirmations" }, 502);

  // 7. Vérification des citations, sans modèle : affirmations, puis questions.
  const { kept, removed, status } = checkClaims(detail.claims, text);
  const questions = checkQuestions(Array.isArray(detail.questions) ? detail.questions : [], text);
  const learned = resolveConcepts(Array.isArray(detail.concepts) ? detail.concepts : [], known.map((c) => c.id));

  // Figures : seuls les labels présents dans la liste extraite sont gardés, trois au plus.
  const chosen = detail.figures ?? [];
  const notes = new Map(chosen.map((f) => [validLabels([f.label], figureRows, 1)[0], f.what_to_look_at]));
  const figures = validLabels(chosen.map((f) => f.label), figureRows, 3)
    .map((label) => ({ label, what_to_look_at: notes.get(label) ?? "" }));

  // 8. Stockage. Concepts et questions vont dans leurs tables, pas dans le JSON du détail.
  const { concepts: _c, questions: _q, ...rest } = detail;
  const row = {
    paper_id: arxivId,
    detail: { ...rest, claims: kept, figures, removed_questions: questions.removed },
    removed_claims: removed,
    verification_status: status,
    text_source: source,
    based_on_abstract: source === "abstract",
    text_truncated: truncated,
    text_mode: textMode,
    model: cfg.detail_model,
    prompt_version: cfg.prompt_version,
    ...(regenerate ? { created_at: new Date().toISOString() } : {}),
  };
  // Première ouverture : si deux ouvertures se croisent, la première écrite gagne et c'est elle
  // qu'on renvoie (la seconde n'écrit ni concepts ni questions). Régénération : on remplace.
  const saved = await db.from("details")
    .upsert(row, { onConflict: "paper_id", ignoreDuplicates: !regenerate })
    .select("paper_id");
  if (saved.error) return json({ error: "database", message: saved.error.message }, 500);
  const won = (saved.data ?? []).length > 0;

  if (won) {
    // Figures choisies : rôle « detail » ; le pipeline les copiera dans le stockage.
    // Après une régénération, les figures qui ne sont plus choisies perdent ce rôle.
    for (const r of figureRows) {
      const note = figures.find((f) => f.label === r.label);
      const roles = r.roles.filter((x) => x !== "detail");
      if (note) roles.push("detail");
      else if (roles.length === r.roles.length) continue;
      await db.from("paper_figures")
        .update(note ? { roles: roles.sort(), what_to_look_at: note.what_to_look_at } : { roles: roles.sort() })
        .eq("paper_id", arxivId).eq("label", r.label);
    }

    if (learningReady) {
      const now = new Date().toISOString();
      const errors: string[] = [];
      const step = async (p: PromiseLike<{ error: { message: string } | null }>) => {
        const { error } = await p;
        if (error) errors.push(error.message);
      };
      // Une fiche existante n'est jamais réécrite : seules les nouvelles sont créées.
      if (learned.new.length) {
        await step(db.from("concepts").upsert(
          learned.new.map((c) => ({ ...c, primary_category: paper.primary_category ?? "", first_paper_id: arxivId })),
          { onConflict: "id", ignoreDuplicates: true },
        ));
      }
      await step(db.from("paper_concepts").delete().eq("paper_id", arxivId));
      if (learned.paper.length) {
        await step(db.from("paper_concepts").upsert(
          learned.paper.map((id, position) => ({ paper_id: arxivId, concept_id: id, position })),
          { onConflict: "paper_id,concept_id", ignoreDuplicates: true },
        ));
      }
      if (learned.links.length) {
        await step(db.from("concept_links").upsert(learned.links.map(([a, b]) => ({ a, b })), { onConflict: "a,b", ignoreDuplicates: true }));
      }
      // Les questions précédentes sont archivées avec leurs réponses, jamais supprimées.
      await step(db.from("questions").update({ archived_at: now }).eq("paper_id", arxivId).is("archived_at", null));
      if (questions.kept.length) {
        await step(db.from("questions").insert(questions.kept.map((q, position) => ({ paper_id: arxivId, position, ...q }))));
      }
      if (errors.length) console.error("open-paper: concepts et questions", arxivId, errors);
    }
  }

  const stored = await db.from("details").select("*").eq("paper_id", arxivId).single();
  return json({ detail: stored.data ?? row, cached: false });
});
