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

## Ce qui existe (V1, flux Aujourd'hui)

| Écran | Fichier | Rôle |
| --- | --- | --- |
| Connexion | `src/app/login.tsx` | E-mail et mot de passe du compte Supabase |
| Today | `src/app/(tabs)/index.tsx` | Date, nombre d'articles, temps estimé, Start / Continue ; écran de fin si l'édition est terminée |
| Cartes | `src/app/edition.tsx` | Une carte par écran, glissement horizontal, progression, feedback, puis fin d'édition |
| Vue profondeur | `src/app/paper/[id].tsx` | État de chargement, explication Curious / Physicist, contexte, affirmations sourcées, lien arXiv |
| Settings | `src/app/(tabs)/settings.tsx` | Compte et déconnexion |

- **Données** (`src/lib/data.ts`) : réseau d'abord, cache du téléphone en secours. Le détail d'un article vient du cache, sinon de la table `details`, sinon de l'Edge Function `open-paper` (première ouverture).
- **Écritures** : feedback, événements de lecture (`shown`, `opened`, `edition_completed`) et fin d'édition passent par une file d'attente gardée sur le téléphone, envoyée dès que le réseau répond.
- **Équations** : texte échappé puis rendu par KaTeX dans une WebView (une iframe sur le web).

## Vérifié le 13 novembre 2026, dans un navigateur, sur le vrai projet

Connexion, accueil, les trois cartes, feedback, vue profondeur d'un article déjà en base, génération d'un article jamais ouvert (état de chargement puis contenu), rendu des équations, écran de fin (2 lus, 1 ignoré), retour à l'accueil sur l'écran de fin. En base : le feedback, les six événements de lecture et `editions.completed_at` sont bien arrivés.

## Pas encore fait ou pas encore vérifié

- Essai sur un téléphone Android avec Expo Go (13 novembre 2026) : connexion, glissement des cartes et rendu des équations confirmés par l'utilisateur. C'est un constat à l'usage, pas une recette détaillée.
- Hors ligne : écrit, non testé.
- KaTeX est chargé depuis Internet : hors ligne, au premier affichage, les équations restent en LaTeX brut.
- Réglages (nombre d'articles, catégories, heures des notifications), notifications push (jeton Expo, projet Firebase) et build APK : étapes suivantes de la spec.
- Carnet, Concepts, Stats : V2.
