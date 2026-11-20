# App Android (Expo)

Dossier `app/` : Expo SDK 58, TypeScript, Expo Router. L'app lit Supabase avec la clé publique et la session du compte propriétaire ; elle n'a jamais la clé Anthropic ni la clé de service.

## Lancer

```bash
cd app
npm install
npm run web        # dans un navigateur, pour développer et vérifier le flux
npm run android    # sur un téléphone ou un émulateur Android (Expo Go)
```

Réglages dans `app/.env` (non commité, modèle dans `app/.env.example`) : adresse du projet et clé **publique**.

Vérifications : `npm run typecheck` et `npm test` (logique pure : état de lecture, feedback, récapitulatif, HTML des équations).

## Construire l'APK

L'APK est construit par le service EAS d'Expo (compte `aa-datascience`, projet `arxiv-digest`), puis installé directement sur le téléphone.

```bash
cd app
npx eas-cli@latest login      # une fois par machine
npx eas-cli@latest build --platform android --profile preview
```

- Le profil `preview` de `app/eas.json` produit un `.apk` et porte l'adresse du projet Supabase et la clé **publique** (le fichier `.env` n'est pas envoyé à Expo).
- La clé de signature Android est générée et conservée par Expo : les versions suivantes s'installent par-dessus la précédente.
- À la fin, le terminal affiche un lien et un code QR : ouvrir le lien sur le téléphone, télécharger l'APK, autoriser l'installation depuis le navigateur.
- Offre gratuite d'Expo : nombre de builds limité par mois, file d'attente possible.
- Icônes (`app/assets/*.png`, source `icon.svg`) : générées par `pipeline/.venv/Scripts/python app/scripts/make_icons.py` depuis la racine. Une page à coin replié portant une oscillation amortie, aux couleurs de `theme.ts`. Changer l'icône demande un nouvel APK.

## Ce qui existe (V1, flux Aujourd'hui)

| Écran | Fichier | Rôle |
| --- | --- | --- |
| Connexion | `src/app/login.tsx` | E-mail et mot de passe du compte Supabase |
| Today | `src/app/(tabs)/index.tsx` | Date, nombre d'articles, temps estimé, Start / Continue ; écran de fin si l'édition est terminée |
| Cartes | `src/app/edition.tsx` | Une carte par écran, glissement horizontal, progression, feedback, puis fin d'édition |
| Vue profondeur | `src/app/paper/[id].tsx` | État de chargement, explication Curious / Physicist, figures, contexte, concepts, questions, Regenerate, lien arXiv. Les affirmations sourcées ne sont plus affichées (20 novembre 2026, jugées illisibles) : elles servent seulement au badge « Quotes found in the paper » |
| Settings | `src/app/(tabs)/settings.tsx` | Compte, état des notifications, entrée vers le profil, déconnexion |
| Notebook (V2) | `src/app/(tabs)/notebook.tsx`, `src/app/notebook/[id].tsx` | Articles sauvegardés, recherche, tags, note, export Markdown et BibTeX |
| Stats (V2) | `src/app/(tabs)/stats.tsx` | Lecture par semaine et par sous-catégorie, sur 4, 8 ou 12 semaines |
| Profil (V2) | `src/app/profile.tsx` | Poids appris, niveaux, catégories suivies, nombre d'articles, heures des notifications |
| Concepts (V2) | `src/app/(tabs)/concepts.tsx`, `src/app/concept/[id].tsx` | Concepts rencontrés, recherche ; fiche avec définitions simple et experte, concepts liés, articles ; fusion d'un doublon |
| Widget (Android) | `src/widget/` | Série d'éditions faites (terminées, ou toutes les cartes vues) et articles lus sur les 7 dernières éditions ; rafraîchi par l'app et toutes les heures en arrière-plan. Enregistré dans `index.ts` (point d'entrée), déclaré dans `app.json` (`react-native-android-widget`) |

- **Données** (`src/lib/data.ts`) : réseau d'abord, cache du téléphone en secours. Le détail d'un article vient du cache, sinon de la table `details`, sinon de l'Edge Function `open-paper` (première ouverture).
- **Écritures** : feedback, événements de lecture (`shown`, `opened`, `edition_completed`) et fin d'édition passent par une file d'attente gardée sur le téléphone, envoyée dès que le réseau répond.
- **Équations** : texte échappé puis rendu par KaTeX dans une WebView (une iframe sur le web).
- **Figures** (`src/components/Figure.tsx`) : une figure en haut de la carte si le modèle en a choisi une ; dans la vue profondeur, une à trois figures avec leur phrase « what to look at » et leur légende ; plein écran avec zoom au toucher. Les images viennent du stockage privé (adresses signées) ou, tant qu'elles n'y sont pas copiées, d'arXiv ; elles sont mises en cache sur le téléphone.

## Vérifié le 13 novembre 2026, dans un navigateur, sur le vrai projet

Connexion, accueil, les trois cartes, feedback, vue profondeur d'un article déjà en base, génération d'un article jamais ouvert (état de chargement puis contenu), rendu des équations, écran de fin (2 lus, 1 ignoré), retour à l'accueil sur l'écran de fin. En base : le feedback, les six événements de lecture et `editions.completed_at` sont bien arrivés.

## Figures : vérifié le 14 novembre 2026, dans un navigateur, sur le vrai projet

Figure affichée en haut d'une carte depuis le stockage privé ; ouverture en plein écran ; ouverture d'un article jamais ouvert : la fonction `open-paper` a choisi trois figures, affichées avec leur phrase « what to look at » et leur légende (formules rendues). Non vérifié dans le navigateur : le zoom (pincement et double appui), à contrôler sur le téléphone ; l'affichage hors ligne.

## APK

Premier APK construit le 14 novembre 2026 (sans les figures) : https://expo.dev/accounts/aa-datascience/projects/arxiv-digest/builds/d3e9afbf-d16f-49aa-ba32-22975bb3c8f4 . Les figures demandent un nouveau build.

## Pas encore fait ou pas encore vérifié

- Essai sur un téléphone Android avec Expo Go (13 novembre 2026) : connexion, glissement des cartes et rendu des équations confirmés par l'utilisateur. C'est un constat à l'usage, pas une recette détaillée.
- Hors ligne : écrit, non testé.
- KaTeX est chargé depuis Internet : hors ligne, au premier affichage, les équations restent en LaTeX brut.
- Réglages (nombre d'articles, catégories, heures des notifications), notifications push (jeton Expo, projet Firebase) et build APK : étapes suivantes de la spec.
- V2, étapes 1 à 3 (carnet, stats, bilan du lundi, profil) : vérifiées dans un navigateur le 15 novembre 2026, pas encore sur téléphone ; détail dans `docs/V2_PLAN.md`, section 8.
- Concepts et questions (V2, étape 4) : pastilles de concepts, section Questions (`src/components/Questions.tsx`) et bouton « Regenerate » dans la vue profondeur ; section « Learning » des Stats ; nouveaux concepts sur l'écran de fin. État dans `docs/V2_PLAN.md`, section 8.
- « Demander à l'article » : étape 5 de la V2, non codée.
