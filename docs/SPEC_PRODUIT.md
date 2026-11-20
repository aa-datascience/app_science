# Spec produit — App de veille arXiv

> Copie de la spec d'origine (Claude Doc d'Antoine, version du 13 novembre 2026), recopiée telle quelle le 20 novembre 2026 pour qu'elle vive dans le dépôt.
> Elle décrit le produit voulu. Quand elle diverge du code, ce sont ces documents qui font foi, dans cet ordre :
> 1. les décisions explicites d'Antoine consignées dans `docs/PASSATION.md` (section « Décisions qui modifient la spec ») ;
> 2. `docs/V2_PLAN.md` (décisions du 14 novembre 2026) ;
> 3. `docs/SPEC.md` (architecture réellement construite : génération en deux temps, vérification des citations sans modèle, figures).

Nov 13, 2026 · Antoine

## 1. Vision et principes

Une app mobile personnelle qui remplace le scroll des réseaux sociaux par une **édition quotidienne d'articles de physique** tirés d'arXiv, transformés en contenu clair et vérifié. L'objectif est d'apprendre et de suivre la recherche, pas de maximiser le temps passé.

Principes non négociables :

- **Un fil qui se termine.** Une édition par jour, avec un nombre d'articles réglable. Une fois terminée, l'app l'affiche clairement et ne propose rien de plus : pas de bouton « encore », pas de suggestions.
- **Tout est sourcé.** Chaque contenu renvoie à l'article arXiv, et chaque affirmation importante doit être appuyée par un passage du texte.
- **Personnalisation transparente.** Elle vient uniquement des feedbacks explicites et de signaux de lecture visibles dans les statistiques. Pas d'optimisation de l'engagement.
- **Motivation sans addiction.** Une notification le matin, un rappel le soir si l'édition n'est pas finie, puis plus rien. Des statistiques de lecture pour se responsabiliser, mais pas de compteur de jours consécutifs, de likes publics ou de mécanique de récompense.

## 2. Décisions arrêtées

| Sujet | Décision |
| --- | --- |
| Domaine | Physique uniquement |
| Source | arXiv (flux quotidiens + texte complet) |
| Langue du contenu | Anglais |
| Utilisateurs | Moi seul (pas de comptes, pas de partage) |
| Plateforme | App Android native (APK installé directement), pas d'iPhone |
| Design | Cartes : une carte par écran, progression visible, fin explicite |
| Rythme | Une édition par jour, publiée le matin ; nombre d'articles réglable |
| Notifications | Une le matin (édition prête) + un rappel le soir si non terminée |
| Formats | Carte, explication à deux niveaux, contexte, concepts prérequis, questions de compréhension. Pas d'audio |
| Mécaniques | Profondeur à la demande, question à l'article, carnet, graphe de concepts + révision espacée, dossier de la semaine, réglage automatique par feedback |

## 3. Architecture technique (gratuite, hors API Claude)

Pas de serveur à louer ni à maintenir. Trois blocs :

1. **GitHub Actions (dépôt privé).** Exécute le pipeline Python chaque nuit (cron), la mise à jour du profil, et deux courtes tâches de notification (matin et soir). Le quota gratuit des dépôts privés suffit largement pour une dizaine de minutes par nuit.
2. **Supabase (offre gratuite).** Base PostgreSQL, API REST générée automatiquement et utilisée directement par l'app, authentification (un seul compte, le mien) et Row Level Security pour que personne d'autre ne puisse lire ou écrire. Une Edge Function `ask-paper` (TypeScript) appelle l'API Claude pour la question à l'article.
3. **App Android (React Native + Expo, TypeScript).** Client supabase-js, cache hors ligne de l'édition du jour (synchronisation des feedbacks au retour du réseau), rendu LaTeX via KaTeX, notifications via expo-notifications.

Choix techniques :

- **IA :** API Claude. Un modèle rapide et bon marché pour le classement, un modèle plus fort pour la génération et la vérification. Modèles configurables. C'est la seule dépense du projet (quelques francs par mois, avec plafond).
- **Secrets :** clé Anthropic et clé de service Supabase dans les secrets GitHub Actions ; clé Anthropic aussi dans les secrets Supabase pour l'Edge Function. L'app n'utilise que la clé publique Supabase plus la session de mon compte.
- **Installation Android :** APK construit avec EAS Build (offre gratuite d'Expo) ou localement, puis installé directement sur le téléphone. Pendant le développement, Expo Go suffit.
- **Push Android :** le service de push d'Expo nécessite un projet Firebase (gratuit) pour les identifiants FCM.

Limites des offres gratuites (conditions à revérifier à la création des comptes) :

- Le cron de GitHub Actions peut être retardé de plusieurs minutes, parfois davantage : lancer le pipeline tôt dans la nuit pour garder de la marge.
- Supabase met en pause les projets gratuits inactifs pendant un certain temps : l'usage quotidien l'évite.
- Si un jour ces limites gênent, le même code Python peut passer sur un petit serveur sans tout réécrire.

## 4. Pipeline quotidien

Lancé chaque nuit par cron, après l'annonce des nouveaux articles arXiv. arXiv n'annonce pas de nouveautés certains jours (week-end) : ces jours-là, l'édition puise dans les bons articles de la semaine non retenus, et le dossier de la semaine (V3) prend le relais. L'horaire exact des annonces arXiv est à vérifier au moment du développement.

**Étape 1 — Ingestion.** Récupérer les nouvelles soumissions des catégories suivies (flux RSS/Atom par catégorie ou API arXiv), y compris les cross-lists. Exclure par défaut les simples nouvelles versions d'articles déjà vus. Respecter les limites d'arXiv (une requête toutes les quelques secondes, User-Agent identifiable). Stocker les métadonnées : identifiant, titre, auteurs, résumé, catégories, date, liens.

Catégories par défaut (modifiables) : cond-mat.supr-con, cond-mat.mes-hall, cond-mat.str-el, quant-ph, hep-ph, hep-th, gr-qc, astro-ph.CO. Le reste de la physique sert de réservoir pour l'emplacement exploration.

**Étape 2 — Présélection (sans IA).** Mots-clés positifs et négatifs, bonus pour les auteurs suivis, poids par catégorie, exclusion des articles déjà montrés. On garde au plus une centaine de candidats.

**Étape 3 — Classement (modèle rapide).** Le modèle lit titre et résumé de chaque candidat avec un résumé du profil, et renvoie en JSON : pertinence, importance, nouveauté, difficulté (notes de 1 à 5) et une phrase « pourquoi cet article ». Score final = combinaison pondérée configurable. Sélection des N meilleurs avec une contrainte de diversité (nombre maximum par sous-catégorie), plus un emplacement exploration.

**Étape 4 — Texte complet.** Dans l'ordre de préférence : version HTML d'arXiv, puis source LaTeX, puis extraction du PDF. HTML et LaTeX conservent les équations proprement. Si seul le résumé est exploitable, l'article est marqué « basé sur le résumé ».

**Étape 5 — Génération (modèle fort).** Un appel par article, sortie JSON stricte selon le schéma de la section 5.

**Étape 6 — Vérification (modèle fort, appel séparé).** Le modèle reçoit le texte de l'article et le contenu généré. Pour chaque affirmation, il cherche le passage qui l'appuie. Les affirmations non appuyées sont corrigées ou supprimées. Si la vérification échoue deux fois, la carte est publiée avec la mention « non vérifié » ou remplacée par un autre article.

**Étape 7 — Publication.** L'édition est marquée prête avant l'heure de la notification du matin.

**Robustesse.** Relances automatiques en cas d'erreur réseau ou d'API, journalisation de chaque étape, plafond de dépense quotidien dans la config. Si le pipeline échoue, l'app affiche une édition de secours (articles en réserve) et signale le problème.

## 5. Formats de contenu générés

Pour chaque article, la génération produit un objet JSON avec les champs suivants (tout en anglais) :

- **card** — titre reformulé en langage clair ; une phrase « ce qu'ils ont trouvé » ; une phrase « pourquoi c'est important » ; tags ; difficulté ; temps de lecture estimé.
- **explanation_lay** — explication pour un curieux cultivé, sans formule (environ 150 à 250 mots).
- **explanation_expert** — explication pour un étudiant en master de physique, avec équations en LaTeX (environ 300 à 500 mots).
- **context** — ce qu'on savait avant ; ce que l'article change ; limites et critiques possibles (champ obligatoire).
- **concepts** — un à trois concepts prérequis, identifiés par un identifiant stable. Si le concept existe déjà en base, il est réutilisé ; sinon une fiche concept est créée (définition simple, définition experte, concepts liés).
- **questions** — deux ou trois questions de compréhension (QCM ou réponse courte), avec réponse et explication.
- **claims** — la liste des affirmations factuelles du contenu, chacune avec la citation de l'article qui l'appuie. Sert à l'étape de vérification et à l'affichage des sources.

Règles de génération :

- Ne jamais inventer de chiffre : toute valeur numérique doit figurer dans l'article.
- Distinguer clairement les résultats des spéculations ou perspectives des auteurs.
- Toujours mentionner les limites.
- Équations en LaTeX, délimitées de façon cohérente pour le rendu KaTeX.
- Les prompts sont stockés comme fichiers versionnés dans le dépôt, et chaque contenu enregistre la version de prompt et le modèle utilisés.

## 6. Personnalisation et feedback

**Profil.** Poids par catégorie arXiv, mots-clés pondérés, auteurs suivis, niveau par sous-domaine (je peux être expert en matière condensée et débutant en cosmologie), et une description libre de mes intérêts, modifiable.

**Feedback explicite sur chaque carte :**

- Intéressant / pas intéressant → ajuste les poids des sujets, catégories et mots-clés.
- Trop facile / trop dur → ajuste le niveau par défaut du sous-domaine.
- Sauvegarder au carnet → signal positif fort.

**Signaux implicites :** carte ouverte en profondeur (lue), carte passée sans ouverture (ignorée), question posée à l'article.

**Mise à jour.** Après chaque édition, petits ajustements des poids, avec un léger retour progressif vers la neutralité pour éviter l'enfermement. Le prompt de classement reçoit un résumé du profil et les titres récemment aimés et rejetés.

**Garde-fous :**

- L'emplacement exploration est toujours présent et n'est jamais supprimé par le feedback.
- Chaque carte affiche une ligne « pourquoi cet article ».
- Un écran Profil montre les poids appris et permet de les modifier à la main.

## 7. App mobile : écrans et interactions

**Navigation :** barre d'onglets en bas — Aujourd'hui, Carnet, Concepts, Stats, Réglages.

**Style visuel :** sobre et typographique, mode sombre, beaucoup d'espace, pas de pastilles rouges ni d'animations de récompense. Les équations sont rendues proprement partout.

### Aujourd'hui

- **Accueil de l'édition :** date, nombre d'articles et temps estimé (par exemple « 8 papers · ~25 min »), bouton Commencer. Si l'édition est finie, on arrive directement sur l'écran de fin.
- **Carte :** une carte par écran, on passe à la suivante par un glissement horizontal. Barre de progression toujours visible (3/8). Contenu : titre clair, ce qu'ils ont trouvé, pourquoi c'est important, tags, ligne « pourquoi cet article », badges « vérifié » ou « basé sur le résumé », marqueur « exploration » le cas échéant. En bas : intéressant / pas intéressant, facile / dur, sauvegarder.
- **Profondeur :** un toucher sur la carte ouvre une vue déroulante avec, dans l'ordre : Explication (bascule Curieux / Physicien), Contexte, Concepts (pastilles qui ouvrent la fiche), Questions, Demander à l'article, Article original (page arXiv ou PDF dans un navigateur intégré).
- **Demander à l'article :** une conversation dont les réponses s'appuient uniquement sur le texte de l'article, avec citations. Si la réponse n'est pas dans l'article, le modèle le dit.
- **Révisions (V3) :** les fiches concepts à réviser ce jour-là sont intégrées à l'édition, avant l'écran de fin, en nombre limité.
- **Fin d'édition :** récapitulatif du jour (lus, ignorés, sauvegardés, nouveaux concepts) et « à demain ». Aucun contenu supplémentaire proposé.

### Carnet

Articles sauvegardés avec notes personnelles, recherche, tags, export Markdown et BibTeX.

### Concepts

Liste des concepts appris, fiche détaillée (définitions simple et experte, concepts liés, articles où il apparaît). Vue graphe en V3.

### Stats

Voir la section 8.

### Réglages

Nombre d'articles par édition, heure de la notification du matin, heure du rappel du soir, catégories suivies, mots-clés, auteurs suivis, niveaux par sous-domaine, poids appris (modifiables), description libre des intérêts.

## 8. Notifications et statistiques

### Notifications

Envoyées par deux tâches GitHub Actions planifiées (matin et soir) via le service de push d'Expo : elles lisent dans Supabase si l'édition est prête ou terminée. L'app enregistre son jeton de push dans Supabase au premier lancement.

- **Matin** (heure réglable, 7h30 par défaut, fuseau Europe/Zurich) : « Today's edition is ready — 8 papers ». Envoyée seulement si l'édition est prête.
- **Soir** (heure réglable, 20h par défaut) : rappel envoyé seulement si l'édition n'est pas terminée, avec le nombre d'articles restants.
- **Rien d'autre**, jamais. Une édition terminée coupe toute notification jusqu'au lendemain matin.

### Statistiques

Définitions :

- **Montré** : la carte est apparue à l'écran.
- **Lu** : la vue profondeur a été ouverte.
- **Ignoré** : la carte a été passée sans ouverture.
- **Édition terminée** : toutes les cartes ont été vues jusqu'à l'écran de fin.

Écran Stats :

- Vue par semaine : articles montrés, lus, ignorés ; taux de lecture global ; éditions terminées sur 7.
- Taux de lecture par sous-catégorie (graphique en barres) : repère les domaines délaissés.
- Articles sauvegardés, questions réussies, nouveaux concepts.
- Évolution sur 4 à 12 semaines.
- Un bilan de la semaine passée affiché en tête de l'édition du lundi.

Pas de compteur de jours consécutifs.

## 9. Modèle de données et API

### Tables

- **papers** — arxiv_id, titre, auteurs, résumé, catégories, catégorie principale, date, version, liens HTML/PDF, source du texte complet (html / latex / pdf / abstract), texte complet.
- **rankings** — paper_id, date, score de présélection, pertinence, importance, nouveauté, difficulté, raison, score final, modèle, version du prompt.
- **editions** — id, date, statut (pending / ready / failed / fallback), heure de disponibilité, heure de fin de lecture.
- **edition_items** — edition_id, paper_id, position, type d'emplacement (main / exploration).
- **contents** — paper_id, JSON généré (section 5), statut de vérification, basé sur le résumé (booléen), modèle, version du prompt, date.
- **concepts** — id stable, nom, définition simple, définition experte. **concept_links** (paires de concepts liés) et **paper_concepts** (liens article-concept).
- **concept_reviews** — concept_id, prochaine échéance, intervalle, facilité, dernier résultat (révision espacée type SM-2).
- **feedback** — paper_id, type (interesting, not_interesting, too_easy, too_hard), date.
- **reading_events** — paper_id, événement (shown, opened, section_viewed, question_asked, edition_completed), section, date.
- **notebook** — paper_id, note, tags, date.
- **qa_messages** — paper_id, rôle, contenu, date.
- **profile** — poids par catégorie, poids des mots-clés, auteurs suivis, niveaux, description des intérêts, réglages (nombre d'articles, heures des notifications, fuseau), jeton de push.
- **weekly_dossiers** — semaine, sujet, contenu, articles liés.
- **api_usage** — date, modèle, tokens entrants et sortants, coût estimé (pour le plafond quotidien).

### Accès aux données

Pas d'API maison : l'app lit et écrit directement dans les tables Supabase, protégées par Row Level Security.

- **Édition du jour :** une vue SQL `edition_today` qui renvoie les cartes dans l'ordre.
- **Contenu d'un article, carnet, concepts, révisions, profil :** lecture et écriture directes sur les tables correspondantes.
- **Feedbacks et événements de lecture :** insertions par lots (synchronisation hors ligne).
- **Statistiques :** une fonction SQL `get_stats(range)`.
- **Question à l'article :** Edge Function `ask-paper`, qui charge le texte de l'article, appelle Claude et enregistre l'échange dans qa_messages.
- **Jeton de push :** stocké dans profile.

## 10. Roadmap

### V1 — Une édition quotidienne utilisable

- Projet Supabase (tables, sécurité RLS, vue de l'édition), dépôt GitHub avec workflows Actions, configuration.
- Pipeline complet : ingestion, présélection, classement (avec la ligne « pourquoi cet article » et l'emplacement exploration), texte complet, génération (carte, deux explications, contexte), vérification, publication par cron.
- App : flux Aujourd'hui (accueil, cartes, vue profondeur, fin d'édition), rendu des équations, boutons de feedback enregistrés, événements de lecture, cache hors ligne.
- Réglages de base : nombre d'articles, catégories, heures des notifications.
- Notifications du matin et du soir.

### V2 — Apprendre et personnaliser

- Réglage automatique du profil par le feedback, écran Profil.
- Fiches concepts (création et réutilisation) et questions de compréhension.
- Demander à l'article.
- Carnet avec notes et export.
- Écran Stats et bilan du lundi.

### V3 — Approfondir

- Graphe de concepts.
- Révision espacée intégrée à l'édition.
- Dossier de la semaine (week-end), qui comble aussi les jours sans annonces arXiv.
- Bouton « signaler une erreur » et tableau de suivi de la qualité des contenus.

## 11. Risques et points ouverts

### Risques

- **Erreurs de contenu.** C'est le risque principal pour de la physique pointue. Parades : génération à partir du texte réel, étape de vérification, citations visibles, et relecture attentive de quelques éditions au début pour ajuster les prompts.
- **Coût de l'API.** Modèle bon marché pour le classement, plafond quotidien, suivi dans api_usage. Le coût réel est à mesurer après une semaine d'usage.
- **arXiv.** Respect des limites de requêtes et des conditions d'utilisation ; la version HTML n'existe pas pour tous les articles.
- **Offres gratuites.** Retards du cron GitHub, mise en pause de Supabase en cas d'inactivité, conditions qui peuvent changer (section 3).
- **Bulle de filtre.** Emplacement exploration et retour progressif vers la neutralité.
- **Stats contre-productives.** Si elles deviennent une source de culpabilité qui décourage, les rendre plus discrètes dans les réglages.

### Points ouverts

- Nombre d'articles par défaut (proposition : 8).
- Modèles Claude exacts pour chaque étape, à fixer selon le coût mesuré.

## 12. Consignes pour Claude Code

**Structure du dépôt (monorepo) :**

- `pipeline/` — Python 3.12 : ingestion arXiv, classement, génération, vérification, mise à jour du profil, envoi des notifications. Pydantic, httpx, SDK Anthropic, client Supabase.
- `.github/workflows/` — workflows planifiés : pipeline de nuit, notification du matin, rappel du soir.
- `supabase/` — migrations SQL (tables, RLS, vue `edition_today`, fonction `get_stats`) et Edge Function `ask-paper`.
- `app/` — Expo + TypeScript, expo-router, expo-notifications, supabase-js, rendu KaTeX.
- `prompts/` — prompts de classement, génération, vérification et question à l'article, versionnés.
- `docs/SPEC.md` — cette spec, exportée en Markdown, référencée dans `CLAUDE.md`.

**Configuration :** secrets dans `.env` (clé API Anthropic, jeton de l'app, URL de la base), jamais commités. Réglages dans `config.yaml` : catégories, modèles, nombre d'articles, pondérations du score, plafond de dépense.

**Ordre de construction :**

1. Pipeline en local, en ligne de commande, sur une journée d'arXiv, qui écrit l'édition en JSON. Relire la qualité des contenus et ajuster les prompts avant d'aller plus loin.
2. Schéma Supabase et écriture du pipeline dans la base.
3. Workflows GitHub Actions (pipeline de nuit, notifications).
4. App Android : flux Aujourd'hui, puis réglages, puis notifications ; build APK.
5. Ensuite seulement, V2 puis V3.

**Qualité du code :**

- Sorties des modèles validées par des schémas Pydantic, avec nouvelle tentative si le JSON est invalide.
- Tests unitaires sur la présélection, le score et la mise à jour du profil, avec des réponses arXiv enregistrées comme données de test. Aucun appel réel à l'API Claude dans les tests.
- Journalisation de chaque étape du pipeline et de chaque appel au modèle (tokens, coût).
- Me demander avant de choisir l'hébergement ou toute dépense.
