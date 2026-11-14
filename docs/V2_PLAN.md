# Plan de la V2

État : **proposition, en attente de validation**. Rien de la V2 n'est codé. Les migrations SQL sont écrites dans `supabase/v2_pending/` et ne sont pas appliquées.

Périmètre (spec d'origine, sections 5, 6, 7 et 10) : (a) profil appris et écran Profil, (b) fiches concepts et questions de compréhension, (c) « Demander à l'article », (d) carnet, (e) statistiques et bilan du lundi.

## 1. Ordre d'implémentation proposé

L'ordre va du moins risqué au plus risqué, et met en premier ce qui ne coûte rien à l'usage.

| Étape | Contenu | Modèle | Pourquoi à cette place |
| --- | --- | --- | --- |
| 1 | **Carnet** (d) | aucun | Le bouton Save existe déjà ; il lui manque une destination. Aucune dépendance. |
| 2 | **Stats et bilan du lundi** (e) | aucun | Les événements de lecture s'accumulent depuis la V1 ; tout est en SQL. |
| 3 | **Profil appris et écran Profil** (a) | aucun | Change ce que le pipeline sélectionne : à faire avant de toucher aux prompts, pour mesurer un effet à la fois. Absorbe aussi les réglages restés en V1 (nombre d'articles, catégories, heures des notifications). |
| 4 | **Concepts et questions** (b) | le même appel qu'aujourd'hui | Modifie le prompt et le schéma du détail : c'est le changement le plus sensible pour la qualité. |
| 5 | **Demander à l'article** (c) | un appel par question | Seule fonctionnalité dont le coût dépend de l'usage ; nouvelle Edge Function. |

Chaque étape se termine par : migration appliquée, tests, essai sur le vrai projet, nouvel APK.

## 2. Changements de schéma

Fichiers dans `supabase/v2_pending/`, vérifiés ensemble sur une copie du schéma actuel (Postgres embarqué) : ils s'appliquent sans erreur, les vues et fonctions renvoient ce qui est attendu, et un compte autre que le propriétaire ne voit aucune ligne.

| Fichier | Ajoute | Écrit par |
| --- | --- | --- |
| `01_notebook.sql` | table `notebook` (note, tags), vue `notebook_entries`, fonction `search_notebook(q)` ; reprend les articles déjà marqués Save | l'app |
| `02_stats.sql` | vue `reading_log`, fonctions `get_stats(weeks)` et `last_week_summary()` | personne (lecture seule) |
| `03_profile.sql` | tables `profile_weights`, `profile_levels`, `profile_changes` ; curseur d'apprentissage dans `profile` | le pipeline et l'app (modifications à la main) |
| `04_concepts_questions.sql` | tables `concepts`, `concept_links`, `paper_concepts`, `questions`, `question_attempts` ; vue `concept_cards` | la fonction `open-paper` ; l'app pour les réponses aux questions |
| `05_ask_paper.sql` | table `qa_messages` | la fonction `ask-paper` |

Deux choix de conception à relever :

- **Les poids quittent `config.yaml`.** En V2 ils vivent en base (`profile_weights`) ; `config.yaml` ne sert plus qu'à les initialiser. Chaque changement est journalisé dans `profile_changes` avec sa raison, pour que l'écran Profil puisse expliquer pourquoi un poids a bougé.
- **L'app ne peut écrire ni concepts, ni questions, ni messages de conversation** : seules les Edge Functions le font, pour que tout contenu généré passe par la vérification.

## 3. Prompts : ce qui change

### Détail (`prompts/detail.md`, même appel qu'aujourd'hui)

Trois champs ajoutés au schéma de sortie :

- `concepts` : 1 à 3 concepts prérequis. Pour chacun, soit l'identifiant d'un concept existant (liste fournie dans le prompt), soit une nouvelle fiche : identifiant stable, nom, définition simple, définition experte, concepts liés.
- `questions` : 2 ou 3 questions (QCM ou réponse courte) avec réponse et explication. Règle : la réponse doit se trouver dans l'article, et chaque question cite le passage qui la fonde, vérifié par le même script que les affirmations.

Nouveau bloc d'entrée : la liste des concepts déjà connus (identifiant et nom), pour la réutilisation.

### Classement (`prompts/rank.md`)

Ajout des titres récemment aimés et rejetés (spec §6), tirés des feedbacks. Quelques centaines de tokens en plus par lot, sur Haiku.

### Demander à l'article (nouveau, `prompts/ask.md`)

Entrée : le texte stocké de l'article (mis en cache), les derniers échanges, la question. Sortie : une réponse courte, la liste des affirmations avec leur citation exacte, et un drapeau « pas dans l'article ». Les affirmations dont la citation est introuvable sont retirées, comme pour les explications.

## 4. Écrans à créer

| Écran | Contenu |
| --- | --- |
| **Carnet** (onglet) | Liste des articles sauvegardés, recherche, filtre par tag ; fiche avec note et tags modifiables ; export Markdown et BibTeX |
| **Stats** (onglet) | Par semaine : montrés, lus, ignorés, taux de lecture, éditions terminées sur 7 ; barres par sous-catégorie ; sélecteur 4 / 8 / 12 semaines |
| **Bilan du lundi** | Carte en tête de l'édition du lundi, avant la première carte |
| **Profil** (dans Réglages) | Poids par catégorie et par mot-clé, niveaux par sous-domaine, modifiables ; dernier changement et sa raison ; réglages V1 restants |
| **Concepts** (onglet) | Liste des concepts rencontrés ; fiche avec les deux définitions, les concepts liés, les articles où il apparaît |
| **Vue profondeur** (compléments) | Pastilles de concepts, section Questions, entrée « Ask the paper » |
| **Demander à l'article** | Conversation avec citations dépliables ; état « pas dans l'article » |

La barre d'onglets passe à cinq : Today, Notebook, Concepts, Stats, Settings (spec §7).

## 5. Surcoût estimé

Ce sont des **estimations**, pas des mesures : elles seront mesurées à chaque étape, comme pour la V1. Base actuelle mesurée : un article ouvert coûte 0,006 à 0,010 $ avec Haiku (0,088 $ avec Sonnet, mesure du 13 novembre).

### Par article ouvert (étape 4 : concepts et questions)

| | Tokens en plus | Haiku 5.5 | Sonnet 5.5 |
| --- | --- | --- | --- |
| Entrée : consignes et liste de concepts connus (plafonnée à 150) | environ 1 500 | 0,00015 $ | 0,003 $ |
| Sortie : 1 à 3 fiches concepts | environ 300 | 0,00015 $ | 0,003 $ |
| Sortie : 2 à 3 questions avec citation | environ 400 | 0,0002 $ | 0,004 $ |
| **Total par article ouvert** | | **environ 0,0005 $** | **environ 0,010 $** |

### Par question posée à l'article (étape 5)

Pour un article de 30 000 tokens, réponse plafonnée à 600 tokens.

| | Haiku 5.5 | Sonnet 5.5 |
| --- | --- | --- |
| Première question (écriture du cache) | environ 0,004 $ | environ 0,08 $ |
| Questions suivantes dans les 5 minutes (lecture du cache) | environ 0,0006 $ | environ 0,009 $ |

### Par mois (8 cartes et 3 articles ouverts par jour)

| | Haiku 5.5 | Sonnet 5.5 |
| --- | --- | --- |
| V1 actuelle, figures comprises | environ 1,1 $ | environ 8,9 $ |
| + concepts et questions | + 0,05 $ | + 0,9 $ |
| + une question à l'article par jour | + 0,12 $ | + 2,4 $ |
| + classement enrichi des titres aimés et rejetés | + 0,01 $ | + 0,01 $ |
| **Total estimé** | **environ 1,3 $** | **environ 12 $** |

Profil, stats et carnet ne coûtent rien : Python et SQL, sans modèle. Avec Sonnet, le total approche le plafond de 15 $ ; une semaine avec plus de trois ouvertures par jour le ferait atteindre.

## 6. Décisions attendues

1. **Modèle du détail.** Le cahier des charges de la V2 parle de Sonnet ; la configuration actuelle est Haiku, à votre demande. La V2 charge davantage cet appel (concepts, questions, figures). Garder Haiku, ou repasser à Sonnet ? Je propose de trancher sur une mesure à l'étape 4, comme pour la V1.
2. **Modification d'un poids à la main.** Deux options : elle déplace le poids et l'apprentissage continue à partir de là, ou elle le verrouille. Le schéma permet les deux (colonne `locked`). Je propose : l'apprentissage continue, avec une case « verrouiller » par ligne.
3. **Portée de l'apprentissage.** Je propose : poids des catégories, poids des mots-clés déjà présents, niveaux par sous-domaine. Pas de nouveaux mots-clés ajoutés tout seuls, pour que le profil reste lisible. D'accord ?
4. **Force de l'apprentissage.** Aujourd'hui dans le code : +0,05 pour « interesting », −0,05 pour « not for me », +0,10 pour Save, retour de 2 % vers la valeur de repos à chaque édition, bornes 0,2 à 2,0. Faut-il aussi compter les signaux implicites (article lu : petit plus ; ignoré : petit moins) ? La spec les cite ; je propose de les compter à un cinquième du poids d'un feedback explicite.
5. **Réutilisation des concepts.** La liste des concepts connus grossit avec le temps. Je propose de n'en passer au modèle que 150 au plus, ceux du même domaine d'abord. Les doublons éventuels (« Andreev bound state » et « Andreev states ») se fusionneraient à la main depuis l'écran Concepts : acceptable ?
6. **Détails déjà générés.** Les articles ouverts avant l'étape 4 n'auront ni concepts ni questions, puisqu'un détail n'est jamais régénéré. Les laisser ainsi, ou autoriser une régénération à la demande (payante) ?
7. **Questions de compréhension.** Garder l'historique des réponses (oui dans le schéma) ? Les résultats doivent-ils influencer le niveau du sous-domaine ? Je propose : historique oui, influence non en V2.
8. **Demander à l'article.** Trois réglages : longueur maximale d'une réponse (je propose environ 150 mots), nombre maximal de questions par jour (je propose 20), mémoire de la conversation (je propose les trois derniers échanges).
9. **Carnet.** Save crée l'entrée du carnet, et la retirer du carnet annule le Save : d'accord ? Export : un fichier Markdown et un fichier BibTeX partagés par le menu de partage d'Android.
10. **Bilan du lundi.** En tête de l'édition (une carte de plus avant la première), ou sur l'écran d'accueil ? La spec dit « en tête de l'édition du lundi ».
11. **Reste de la V1.** Notifications push (projet Firebase à créer) et réglages ne sont pas faits. Les réglages entrent naturellement dans l'étape 3. Les notifications : avant la V2, ou après ?

## 7. Ce qui n'est pas dans la V2

Graphe de concepts, révision espacée, dossier de la semaine, bouton « signaler une erreur » : V3 (spec §10).
