// Scénario de l'étape 4 de la V2 sur un Postgres embarqué : RLS des concepts et questions,
// archivage des questions d'un détail régénéré, fusion de deux concepts, compteurs de get_stats.
// Depuis supabase/check :  node check_concepts.mjs
import { PGlite } from "@electric-sql/pglite";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const db = new PGlite();
await db.exec(`
  create role anon nologin; create role authenticated nologin; create role service_role nologin bypassrls;
  create schema auth;
  create function auth.uid() returns uuid language sql stable as $f$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $f$;
  grant usage on schema auth to anon, authenticated;
  create schema storage;
  create table storage.buckets (id text primary key, name text, public boolean, file_size_limit bigint, allowed_mime_types text[]);
  create table storage.objects (id bigserial primary key, bucket_id text, name text);
  alter table storage.objects enable row level security;
  alter default privileges in schema public grant all on tables to anon, authenticated, service_role;
  alter default privileges in schema public grant all on sequences to anon, authenticated, service_role;
  alter default privileges in schema public grant execute on functions to anon, authenticated, service_role;
`);
const dir = join(root, "supabase/migrations");
for (const f of readdirSync(dir).filter((x) => x.endsWith(".sql")).sort()) await db.exec(readFileSync(join(dir, f), "utf-8"));

const OWNER = "11111111-1111-1111-1111-111111111111", OTHER = "22222222-2222-2222-2222-222222222222";
const ok = (cond, msg) => { if (!cond) { console.error("ÉCHEC", msg); process.exitCode = 1; } else console.log("ok  ", msg); };
await db.exec(`
  insert into app_owner values ('${OWNER}');
  insert into papers (arxiv_id, title, abstract) values ('p1','T1','A'), ('p2','T2','A');
  insert into concepts (id, name, simple_definition, expert_definition, first_paper_id, created_at)
    values ('josephson-effect','Josephson effect','s','e','p1', now() - interval '1 day'),
           ('josephson-junction-effect','Josephson effect (dup)','s','e','p2', now()),
           ('andreev-reflection','Andreev reflection','s','e','p1', now());
  insert into concept_links values ('andreev-reflection','josephson-junction-effect');
  insert into paper_concepts values ('p1','josephson-effect',0), ('p2','josephson-junction-effect',0), ('p1','andreev-reflection',1);
  insert into questions (paper_id, position, kind, prompt, options, answer, explanation, quote)
    values ('p1',0,'mcq','Q?','["a","b"]','a','x','quote one'), ('p1',1,'short','Q2?','[]','ans','x','quote two');
`);

// Un second jeu de questions courant pour la même position est refusé ; archivé, il passe.
let dupRefused = false;
try { await db.exec(`insert into questions (paper_id, position, kind, prompt, answer, explanation, quote) values ('p1',0,'short','Q','a','x','q')`); }
catch { dupRefused = true; }
ok(dupRefused, "une seule question courante par position");
await db.exec(`update questions set archived_at = now() where paper_id = 'p1';
  insert into questions (paper_id, position, kind, prompt, answer, explanation, quote) values ('p1',0,'short','Q new','a','x','q');`);
ok((await db.query(`select count(*)::int n from questions where paper_id='p1'`)).rows[0].n === 3, "anciennes questions archivées, pas supprimées");

// Côté app : l'autre compte ne voit rien et ne peut pas répondre.
await db.exec(`set role authenticated; set request.jwt.claim.sub = '${OTHER}';`);
ok((await db.query(`select * from concept_cards`)).rows.length === 0, "autre compte : aucun concept visible");
let refused = false;
try { await db.exec(`insert into question_attempts (question_id, answer, correct) values (1, 'a', true)`); } catch { refused = true; }
ok(refused, "autre compte : réponse refusée");
refused = false;
try { await db.query(`select merge_concepts('josephson-junction-effect','josephson-effect')`); } catch { refused = true; }
ok(refused, "autre compte : fusion refusée");

// Propriétaire.
await db.exec(`set request.jwt.claim.sub = '${OWNER}';`);
await db.exec(`insert into question_attempts (question_id, answer, correct) values (1, 'a', true), (1, 'b', false), (2, '', false)`);
refused = false;
try { await db.exec(`insert into concepts (id, name, simple_definition, expert_definition) values ('x','x','x','x')`); } catch { refused = true; }
ok(refused, "propriétaire : l'app ne peut pas écrire de concept");
refused = false;
try { await db.exec(`insert into questions (paper_id, position, kind, prompt, answer, explanation, quote) values ('p2',0,'short','Q','a','x','q')`); } catch { refused = true; }
ok(refused, "propriétaire : l'app ne peut pas écrire de question");

const cards = (await db.query(`select id, paper_count, papers, related from concept_cards order by id`)).rows;
ok(cards.length === 3, "propriétaire : trois fiches");
await db.query(`select merge_concepts('josephson-junction-effect','josephson-effect')`);
const after = Object.fromEntries((await db.query(`select id, paper_count, related, first_paper_id from concept_cards`)).rows.map((r) => [r.id, r]));
ok(!after["josephson-junction-effect"], "fusion : le doublon disparaît");
ok(after["josephson-effect"].paper_count === 2n || after["josephson-effect"].paper_count === 2, "fusion : ses articles passent à la fiche gardée");
ok(JSON.stringify(after["josephson-effect"].related) === '["andreev-reflection"]', "fusion : ses liens passent à la fiche gardée");
ok(after["josephson-effect"].first_paper_id === "p1", "fusion : l'article de création le plus ancien est gardé");

const stats = (await db.query(`select get_stats(4) s`)).rows[0].s;
console.log(JSON.stringify(stats));
ok(Array.isArray(stats.weeks), "get_stats répond");
// Ajoute une semaine affichée pour voir les compteurs.
await db.exec(`reset role;
  insert into editions (date, status) values (current_date, 'ready');
  insert into edition_items (edition_date, paper_id, position, slot) values (current_date, 'p1', 0, 'main');
  insert into reading_events (paper_id, edition_date, event) values ('p1', current_date, 'shown');
  set role authenticated; set request.jwt.claim.sub = '${OWNER}';`);
const w = (await db.query(`select get_stats(4) s`)).rows[0].s.weeks.at(-1);
console.log(JSON.stringify(w));
ok(w.questions_answered === 2 && w.questions_correct === 1, "stats : 2 questions répondues (première réponse), 1 réussie");
ok(w.new_concepts === 2, "stats : nouveaux concepts de la semaine (après fusion)");
