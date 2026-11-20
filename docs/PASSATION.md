# Passation — reprise du projet par un autre compte Claude

Rédigé le 20 novembre 2026, à la fin de la V1 et des étapes 1 à 3 de la V2. Ce document suffit pour reprendre le travail : il dit quoi faire, dans quel ordre, avec quels accès, et selon quelles règles. `CLAUDE.md` (chargé automatiquement) renvoie ici.

## 0. Ta mission

Construire la suite de l'app, dans cet ordre, **une étape à la fois, chacune sur validation explicite d'Antoine** :

1. **V2, étape 4 — Concepts et questions** (plan détaillé : `docs/V2_PLAN.md`, sections 1 à 6).
2. **V2, étape 5 — « Demander à l'article »** (même document).
3. **V3** — graphe de concepts, révision espacée intégrée à l'édition, dossier de la semaine, bouton « signaler une erreur » (`docs/SPEC_PRODUIT.md`, sections 7, 9 et 10). Il n'existe pas encore de plan : le premier travail de la V3 est d'écrire `docs/V3_PLAN.md` sur le modèle de `docs/V2_PLAN.md` (ordre, schéma, prompts, écrans, surcoût estimé, questions à trancher), puis de le faire valider avant toute ligne de code.

Avant de commencer une étape : relire sa partie du plan, dire à Antoine ce que tu vas faire et ce que ça coûtera, attendre son accord.

## 1. À lire d'abord, dans cet ordre

| Fichier | Pour quoi |
| --- | --- |
| `CLAUDE.md` | Règles du dépôt, commandes. Elles priment. |
| ce fichier | Contexte, accès, décisions, méthode. |
| `docs/SPEC_PRODUIT.md` | Le produit voulu (spec d'origine d'Antoine). |
| `docs/SPEC.md` | Ce qui a réellement été construit, et pourquoi c'est différent de la spec d'origine. |
| `docs/V2_PLAN.md` | Plan de la V2, décisions du 14 novembre, état d'avancement (section 8). |
| `docs/SUPABASE.md`, `docs/APP.md`, `docs/GITHUB_ACTIONS.md` | Mise en service et état de chaque bloc. |
| `docs/VERIFICATIONS_TELEPHONE.md` | Ce qu'Antoine vérifie sur son téléphone après chaque APK. |

## 2. Qui est Antoine, comment travailler avec lui

- Étudiant en master de physique à l'ETH Zurich. Seul utilisateur de l'app (un téléphone Android).
- Il écrit en français, parfois en anglais : **répondre dans la langue de son dernier message.**
- Il veut un **point après chaque fonctionnalité** : ce qui est fait, ce qui est vérifié, ce qui ne l'est pas, ce que ça coûte.
- Il veut qu'on lui **signale toute hausse du coût mesuré** due à une fonctionnalité.
- Il ne lit pas le code : expliquer les choix en termes d'usage, sans jargon inutile.
- Il ne tape pas de commandes : c'est toi qui lances tests, builds et déploiements. Lui installe l'APK et coche la liste de vérifications sur son téléphone.

## 3. Accès dont tu as besoin (à demander à Antoine s'ils manquent)

Aucun secret n'est dans le dépôt. Antoine doit te les fournir **par le fichier `.env` à la racine** (jamais dans le chat, jamais commité) ou se connecter lui-même aux services.

| Accès | Où | Sert à |
| --- | --- | --- |
| Dépôt GitHub `aa-datascience/app_science` (privé, branche `main`) | droits d'écriture pour ton compte ou ta machine | pousser le code ; GitHub Actions tourne dessus |
| `.env` à la racine : `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_PUBLISHABLE_KEY` | copie du `.env` d'Antoine (modèle : `.env.example`) | pipeline, essais payants, lectures de contrôle en base |
| Projet Supabase `zrktdpmmxistgzrejkrs` | tableau de bord supabase.com (compte d'Antoine), ou `npx supabase login` | appliquer les migrations, déployer les Edge Functions, secrets des fonctions |
| Expo / EAS, compte `aa-datascience`, projet `arxiv-digest` | `npx eas-cli@latest login` | construire l'APK |
| Firebase `arxiv-digest-e1b6a` | console Firebase d'Antoine | seulement si les notifications push sont touchées (clé FCM V1 déjà chez Expo) |

Identifiants publics, déjà dans le dépôt et sans danger : URL Supabase et clé publique (`app/eas.json`), identifiant de projet EAS (`app/app.json`).

Secrets déjà en place côté services (ne pas les redemander) : GitHub Actions `ANTHROPIC_API_KEY`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` ; Edge Functions Supabase `ANTHROPIC_API_KEY`.

Règles de sécurité, sans exception :

- Ne jamais commiter `.env`, ne jamais mettre de clé dans `.env.example`, ni dans un fichier suivi, ni dans un message de commit. Vérifier le diff indexé avant chaque commit.
- Ne jamais saisir toi-même un mot de passe ou une clé secrète dans un formulaire web : Antoine le fait.
- La clé de compte de service Firebase ne va jamais dans le dépôt.

## 4. État au 20 novembre 2026

**Fait et en service :**

- Pipeline de nuit (GitHub Actions, `nightly.yml`, vers 05:20–06:20 heure de Zurich) : ingestion arXiv, présélection, classement et cartes par Claude Haiku, édition écrite dans Supabase. Le profil appris est mis à jour avant chaque édition.
- Détail d'un article généré **à l'ouverture** par l'Edge Function `open-paper` (Haiku), citations vérifiées **sans modèle** (`citations.py` / `citations.ts`), figures choisies copiées dans le stockage.
- Notifications du matin et du soir (`notify.yml`, toutes les heures sur les plages horaires, l'heure se règle dans l'app).
- App Android (Expo) : édition du jour, vue détaillée, figures, hors ligne, carnet (notes, tags, export Markdown et BibTeX), Stats et bilan du lundi, écran Profil (poids appris, niveaux, catégories, nombre d'articles, heures), widget d'écran d'accueil (série et articles lus), icône.
- Dernier APK : n° 6, du 19 novembre 2026.
- Coût mesuré : environ 1 $ par mois, plafond mensuel 15 $ (`budget.monthly_usd`).

**Codé mais pas encore vérifié sur le téléphone :** sections 7 à 10 de `docs/VERIFICATIONS_TELEPHONE.md` (carnet, stats, profil, widget, retour à la première carte d'une nouvelle édition). Le rappel du soir n'a pas encore été observé de bout en bout.

**Pas commencé :** V2 étapes 4 et 5 (leurs migrations sont écrites dans `supabase/v2_pending/`, **non appliquées**), V3.

## 5. Décisions qui modifient la spec

La spec d'origine (`docs/SPEC_PRODUIT.md`) date du 13 novembre. Depuis, Antoine a décidé :

| Date | Décision |
| --- | --- |
| 13 nov. | Génération en deux temps : cartes la nuit (titre et résumé), détail à l'ouverture. Vérification des citations par recherche de texte, sans second appel au modèle (`docs/SPEC.md`). |
| 14 nov. | Décisions de la V2 : `docs/V2_PLAN.md`, section 6 (force de l'apprentissage, carnet, bilan du lundi, Demander à l'article : 200 mots, 10 questions par jour, mémoire limitée à l'article, etc.). |
| 19 nov. | **Widget de série** demandé explicitement par Antoine, alors que la spec exclut un compteur de jours consécutifs. Une édition compte comme faite si l'écran de fin est atteint ou si toutes ses cartes ont été vues. Le garder ; ne pas ajouter d'autre mécanique de récompense sans qu'il le demande. |
| 20 nov. | **Claude Haiku partout** : classement, cartes, détail, et toute nouvelle fonction (concepts, questions, Demander à l'article, dossier de la semaine). Ne pas proposer Sonnet ; ne pas changer les modèles de `config.yaml`. |

Le plafond mensuel reste à 15 $.

## 6. Méthode de travail (celle des étapes 1 à 3)

Pour chaque étape :

1. **Plan validé.** Relire la partie du plan, annoncer le travail et le surcoût estimé, attendre l'accord d'Antoine. Toute dépense (pipeline sans `--no-llm`, `open`, `compare`, essais de l'Edge Function) se demande avant.
2. **Migration.** Partir du fichier de `supabase/v2_pending/`, le relire contre le code actuel, le renommer en `supabase/migrations/AAAAMMJJHHMMSS_nom.sql`. Le vérifier sur un Postgres embarqué : `cd supabase/check && npm install && node check_schema.mjs`. Puis l'appliquer au vrai projet (voir section 7). Antoine a demandé que les migrations soient appliquées au fur et à mesure, une fois l'étape validée. Consigner la date dans `docs/SUPABASE.md`.
3. **Code et tests.** Pipeline : `pytest` ; Edge Function : tests `node --test` ; app : `npm run typecheck` et `npm test`. Aucun appel réel à l'API Claude dans les tests.
4. **Essai sur le vrai projet.** App dans un navigateur (`cd app && npm run web`, http://localhost:8081, compte d'Antoine) ; lectures de contrôle en base avec la clé de service. Nettoyer toute donnée d'essai écrite dans la vraie base, et le dire.
5. **Coût mesuré.** Après un essai payant, comparer au coût de base (environ 0,006 à 0,010 $ par article ouvert avec Haiku) et le signaler.
6. **Docs.** Mettre à jour `docs/V2_PLAN.md` (section 8), `docs/APP.md`, `CLAUDE.md` si une règle change, et ajouter une section à `docs/VERIFICATIONS_TELEPHONE.md`.
7. **Commit et push** sur `main` (messages en français, un commit par fonctionnalité), vérifier que le workflow « Tests » passe sur GitHub.
8. **APK** : `cd app && npx eas-cli@latest build --platform android --profile preview --non-interactive --no-wait`, puis suivre avec `eas build:view <id> --json`. Donner à Antoine le lien de la page du build. Une file d'attente de 30 minutes est normale (offre gratuite).
9. **Point** à Antoine : fait, vérifié, non vérifié, coût, ce qu'il doit cocher sur le téléphone.

## 7. Recettes

**Appliquer une migration au vrai projet.** Elles ont été appliquées jusqu'ici par l'éditeur SQL du tableau de bord Supabase (SQL Editor → coller → Run). Deux possibilités :

- Antoine colle lui-même le fichier dans l'éditeur SQL et lance ; ou
- tu le fais dans son navigateur s'il t'en donne l'accès. Dans l'éditeur (Monaco), cliquer sur Run peut ne rien faire : donner le focus à l'éditeur puis Ctrl+Entrée.

**Ne pas utiliser `supabase db push`** : l'historique des migrations du projet n'a pas été tenu par la CLI, elle tenterait de tout réappliquer.

**Déployer une Edge Function.** `open-paper` a été déployée depuis le tableau de bord (Edge Functions → Via Editor, fichiers identiques au dépôt). Avec la CLI : `npx supabase login`, `npx supabase link --project-ref zrktdpmmxistgzrejkrs`, `npx supabase functions deploy <nom>`. Le modèle, les prix, le plafond et les prompts d'une fonction sont lus dans la table `server_config`, que le pipeline réécrit chaque nuit depuis `config.yaml` et `prompts/` : une nouvelle fonction doit suivre le même chemin.

**Lecture de contrôle en base** (depuis `pipeline/`) : petit script Python avec `httpx` et `python-dotenv`, en-têtes `apikey` et `Authorization: Bearer <SUPABASE_SERVICE_KEY>` lus dans `../.env`, sur `<SUPABASE_URL>/rest/v1/<table>`.

**Environnement Windows.** PowerShell 5.1 et Git Bash. Venv : `pipeline/.venv/Scripts/python`. Les guillemets imbriqués dans les commandes cassent facilement : pour une modification délicate, écrire un petit script Python dans un fichier temporaire et le lancer. Le CLI `gh` n'est pas installé : vérifier les workflows sur la page GitHub Actions.

## 8. Étape 4 — Concepts et questions : par où commencer

- Plan : `docs/V2_PLAN.md`, sections 2 (schéma), 3 (prompt du détail et du classement), 4 (écrans), 5 (surcoût : environ +0,05 $ par mois avec Haiku), 6 (décisions 5, 6, 7).
- Migration écrite : `supabase/v2_pending/04_concepts_questions.sql`.
- À toucher : `prompts/detail.md`, `pipeline/arxiv_digest/models.py` (schéma Pydantic du détail), `supabase/functions/open-paper/` (même appel, sortie plus riche, écriture des concepts et questions côté serveur — l'app ne les écrit jamais), onglet Concepts et section Questions de la vue détaillée dans `app/src/app/`, bouton « régénérer » (payant, à la demande).
- Reporté de l'étape 3 : ajouter au prompt de classement (`prompts/rank.md`) les titres récemment aimés et rejetés.
- Règles de parité : toute modification de `citations.py` / `citations.ts` ou de `figures.py` / `figures.ts` se fait des deux côtés, avec un cas dans les fichiers de `pipeline/tests/fixtures/`.

## 9. Étape 5 — Demander à l'article

- Plan : `docs/V2_PLAN.md` (prompt `prompts/ask.md`, décision 8, surcoût). Migration écrite : `supabase/v2_pending/05_ask_paper.sql`.
- Nouvelle Edge Function, sur le modèle de `open-paper` : session du propriétaire seulement, texte de l'article lu en base, cache de prompt pour les questions suivantes, citations vérifiées par `citations.ts`, plafond mensuel respecté, 10 questions par jour.
- C'est la seule fonction dont le coût dépend de l'usage : mesurer et signaler.

## 10. V3

Rien n'est conçu au-delà de la spec. Éléments de départ dans `docs/SPEC_PRODUIT.md` :

- **Graphe de concepts** : tables `concept_links` et `paper_concepts` (créées par l'étape 4), vue graphe dans l'onglet Concepts.
- **Révision espacée** : table `concept_reviews` (type SM-2) ; les fiches à réviser s'insèrent dans l'édition, avant l'écran de fin, en nombre limité.
- **Dossier de la semaine** (week-end) : table `weekly_dossiers` ; comble aussi les jours sans annonce arXiv. Ce sera un appel Haiku de plus par semaine : l'estimer.
- **« Signaler une erreur »** et tableau de suivi de la qualité des contenus.

Écrire `docs/V3_PLAN.md`, le faire valider, puis suivre la méthode de la section 6.

## 11. Pièges connus

- Un écran resté ouvert d'un jour à l'autre voit arriver la nouvelle édition : tout ce qui dépend de la date doit la prendre de l'écran, pas de l'état global (corrigé le 19 novembre dans `edition.tsx`).
- Profil appris : les signaux implicites ne sont appris que pour les éditions remplacées par une plus récente (`profile.py`). Lancer `python -m arxiv_digest profile` à la main fait avancer ce curseur.
- La vraie base est aussi la base d'essai : toute écriture faite en testant reste dans les stats et le profil d'Antoine. L'éviter, ou nettoyer et le dire.
- Le cron de GitHub peut partir avec du retard ; le pipeline refuse de refaire une édition déjà prête.
- `app/src/widget/index.web.ts` neutralise le widget sur le web : tout module natif Android doit faire de même pour que `npm run web` continue de marcher.
