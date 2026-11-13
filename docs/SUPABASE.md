# Mise en service de Supabase

À faire une fois. Les libellés des menus Supabase peuvent avoir légèrement changé.

## 1. Projet et compte

1. Créer un projet sur supabase.com (offre gratuite, région en Europe).
2. **Authentication → Users → Add user** : créer votre compte (e-mail et mot de passe). Noter son identifiant (UUID).
3. **Authentication → Sign In / Providers** : désactiver « Allow new users to sign up ». La base refuse de toute façon tout compte qui n'est pas le propriétaire, mais autant ne pas en laisser créer.

4. **Integrations → Data API** : activer « Enable Data API » si ce n'est pas déjà fait, avec le schéma `public` exposé. Sans cela, toute requête à la base renvoie une erreur 503 `PGRST002` (« Could not query the database for the schema cache »).

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

- Vérifié sur le vrai projet (13 novembre 2026) : la migration, l'écriture d'une édition par le pipeline (3 cartes, 115 articles classés, texte complet des articles de l'édition), la vue `edition_today`, l'ouverture d'un article par la commande `open` avec le texte lu en base, et le fait qu'un second `open` ne régénère rien. Sans clé, l'API répond 401.
- Vérifié hors Supabase, dans un Postgres embarqué : les règles RLS bloquent tout compte autre que le propriétaire.
- Vérifié : la vérification des citations donne les mêmes résultats en Python et en TypeScript (`node --test supabase/functions/open-paper/citations.test.ts`).
- Edge Function `open-paper` : déployée le 13 novembre 2026 depuis l'éditeur du tableau de bord (**Edge Functions → Deploy a new function → Via Editor**, deux fichiers : `index.ts` et `citations.ts`, identiques au dépôt). Sans session, elle répond 401.
- Vérifié sur le vrai projet avec la clé publique seule (sans session) : toutes les tables et la vue renvoient zéro ligne ou un refus, et l'écriture d'un feedback est refusée.
- Vérifié sur le vrai projet avec la session du propriétaire (13 novembre 2026, `scripts/test_open_paper.py`) : lecture de `edition_today` (3 cartes), puis `open-paper` a généré, vérifié et stocké le détail d'un article (statut `verified`, 8 affirmations sourcées).
- **Pas encore vérifié** : l'appel depuis l'app elle-même.

## Deux réglages de la fonction à faire à la main

1. **Edge Functions → Secrets** : ajouter `ANTHROPIC_API_KEY` (fait le 13 novembre 2026). Sans elle, la fonction échoue à la génération.
2. **Edge Functions → open-paper → Settings → « Verify JWT with legacy secret »** : laissé activé ; il ne bloque pas la session du propriétaire (testé). À ne désactiver que si l'app recevait un 401 avec une session valide.

