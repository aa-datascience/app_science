// Vérifie qu'une migration s'applique, sans toucher au vrai projet : Postgres embarqué (PGlite),
// avec ce que Supabase fournit (rôles, auth.uid(), schéma storage) simulé.
//
// Depuis supabase/check :  npm install   puis
//   node check_schema.mjs                     -> supabase/migrations
//   node check_schema.mjs supabase/v2_pending -> les migrations, puis ce dossier en plus
//
// Pour tester une règle RLS : se faire passer pour le propriétaire avec
//   set role authenticated; set request.jwt.claim.sub = '<uuid>';
// (la fonction is_owner() de la migration init compare auth.uid() au propriétaire).
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

for (const dir of ["supabase/migrations", ...process.argv.slice(2)]) {
  for (const f of readdirSync(join(root, dir)).filter((x) => x.endsWith(".sql")).sort()) {
    await db.exec(readFileSync(join(root, dir, f), "utf-8"));
    console.log("ok  ", `${dir}/${f}`);
  }
}
console.log("Toutes les migrations s'appliquent.");
