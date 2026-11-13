# Mise en service de Supabase

À faire une fois. Les libellés des menus Supabase peuvent avoir légèrement changé.

## 1. Projet et compte

1. Créer un projet sur supabase.com (offre gratuite, région en Europe).
2. **Authentication → Users → Add user** : créer votre compte (e-mail et mot de passe). Noter son identifiant (UUID).
3. **Authentication → Sign In / Providers** : désactiver « Allow new users to sign up ». La base refuse de toute façon tout compte qui n'est pas le propriétaire, mais autant ne pas en laisser créer.

## 2. Schéma

Dans **SQL Editor**, coller et exécuter le contenu de `supabase/migrations/20261113000000_init.sql`, puis déclarer le propriétaire :

```sql
insert into app_owner values ('UUID-DE-VOTRE-COMPTE');
```

## 3. Pipeline

Dans `.env`, à la racine du dépôt (jamais commité) :

```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=...      # clé « service_role » / secrète : Project Settings → API
```

Dès que ces deux variables existent, le pipeline lit et écrit son état en base (articles déjà montrés, réserve, coûts du mois) et garde une copie locale de l'édition dans `out/`.

```bash
cd pipeline
.venv/Scripts/python -m arxiv_digest run --size 3
```

Vérifier ensuite dans **Table Editor** : `editions` (statut `ready`), `edition_items`, `cards`, `papers` (colonne `full_text` remplie pour les articles de l'édition), `server_config`, `api_usage`.

Pour tester le détail sans l'app, la commande `open` passe par la base :

```bash
.venv/Scripts/python -m arxiv_digest open 2611.01234
```

## 4. Edge Function `open-paper`

Elle demande la CLI Supabase, utilisable sans installation avec `npx` :

```bash
npx supabase login
npx supabase link --project-ref REF-DU-PROJET
npx supabase secrets set ANTHROPIC_API_KEY=sk-ant-...
npx supabase functions deploy open-paper
```

La fonction lit son modèle, ses prix, son plafond et ses prompts dans la table `server_config`, que le pipeline réécrit chaque nuit à partir de `config.yaml` et de `prompts/` : lancer le pipeline au moins une fois avant de l'appeler.

Elle n'accepte que la session du propriétaire ; elle sera appelée par l'app (`supabase.functions.invoke("open-paper", { body: { arxiv_id } })`).

## Ce qui est vérifié, et ce qui ne l'est pas

- Vérifié hors Supabase : la migration s'applique dans un Postgres embarqué, les écritures du pipeline y passent (y compris une nuit relancée), la vue `edition_today` renvoie les cartes dans l'ordre, et les règles RLS bloquent tout compte autre que le propriétaire.
- Vérifié : la vérification des citations donne les mêmes résultats en Python et en TypeScript (`node --test supabase/functions/open-paper/citations.test.ts`).
- **Pas encore vérifié** : le pipeline contre un vrai projet Supabase, et l'Edge Function elle-même, qui n'a jamais été exécutée.
