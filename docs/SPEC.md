# Spec — App de veille arXiv

La spec d'origine (vision, écrans, modèle de données, roadmap) vit dans le doc Claude : https://claude.ai/artifact/UwA6F5SyJoEBed6hUUdTYy

Ce fichier décrit l'**architecture de génération en vigueur dans le code**. Elle remplace les sections 4 (étapes 4 à 6), 5 et une partie de la section 9 du doc d'origine, qui décrivaient une génération complète de chaque article la nuit, suivie d'une vérification par le modèle.

## Principes inchangés

- Une édition par jour, N articles (8 par défaut), un emplacement exploration toujours présent.
- Tout contenu est sourcé ; aucun chiffre inventé.
- Infrastructure gratuite hors API Claude : GitHub Actions (dépôt privé), Supabase, app Android Expo.
- Demander avant toute dépense ou tout choix d'hébergement.

## Génération en deux temps

Raison : générer et vérifier chaque article la nuit avec un modèle fort coûte de l'ordre de plusieurs dizaines de dollars par mois, alors que seule une partie des articles est réellement ouverte.

### 1. La nuit : l'édition, faite de cartes

Pipeline lancé par cron (GitHub Actions), `python -m arxiv_digest run --batch`.

1. **Ingestion** des flux arXiv des catégories suivies et du réservoir d'exploration ; nouvelles soumissions et cross-lists, sans les simples nouvelles versions.
2. **Présélection sans IA** : poids par catégorie, mots-clés, auteurs suivis ; une centaine de candidats au plus.
3. **Classement** par le modèle rapide (`models.rank`) sur titre et résumé : pertinence, importance, nouveauté, difficulté, phrase « pourquoi cet article ». Sélection des N meilleurs avec contrainte de diversité, plus l'emplacement exploration.
4. **Cartes** par `models.card` (Haiku), **à partir du titre et du résumé seulement**, via l'API Message Batches (-50 %) : titre en langage clair, ce qu'ils ont trouvé, pourquoi c'est important, tags, difficulté.
5. **Publication** de l'édition (statut `ready`).

La nuit, aucun texte complet n'est envoyé à un modèle. À l'étape Supabase, le pipeline de nuit récupérera et stockera en base le texte complet des articles de l'édition (opération gratuite), pour que l'ouverture d'un article n'ait pas à le télécharger.

### 2. À l'ouverture d'une carte : le détail

Déclenché par l'app quand une carte est ouverte pour la première fois ; en ligne de commande, `python -m arxiv_digest open <arxiv_id>` simule cette ouverture.

1. Si le détail existe déjà en base, il est renvoyé tel quel : **un détail n'est jamais régénéré**.
2. Sinon, si le plafond mensuel le permet : texte complet de l'article (HTML arXiv, sinon source LaTeX, sinon PDF, sinon résumé ; option `fulltext.mode: sections`).
3. **Un seul appel** au modèle du détail (`models.generate`) : explication pour curieux, explication pour physicien, contexte (avant, ce que l'article change, limites), et liste d'affirmations, chacune avec une **citation exacte** de l'article.
4. **Vérification des citations sans modèle** (voir ci-dessous).
5. Stockage en base, puis affichage.

**Côté serveur** : une Edge Function Supabase `open-paper` (à écrire à l'étape Supabase), qui prend un identifiant d'article, applique les étapes ci-dessus et renvoie le détail. Elle porte la clé Anthropic ; l'app ne l'a jamais. La vérification des citations y est portée en TypeScript à l'identique de `pipeline/arxiv_digest/citations.py`, avec les mêmes cas de test.

**Côté app** : la vue profondeur affiche d'abord la carte et un **état de chargement** (« Preparing this paper… », quelques dizaines de secondes au premier accès), puis le détail. Si la génération échoue ou si le plafond mensuel est atteint, la vue le dit clairement et propose l'article original sur arXiv. Un article déjà ouvert s'affiche immédiatement, y compris hors ligne une fois mis en cache.

### Vérification des citations (sans appel au modèle)

- Chaque affirmation fournie par le modèle porte une citation de l'article.
- Un script cherche chaque citation dans le texte envoyé au modèle, avec une correspondance tolérante : casse, espaces, ponctuation et mise en forme LaTeX sont ignorés.
- Une affirmation dont la citation est introuvable est **retirée**.
- Si plus d'un tiers des affirmations échouent (ou s'il n'y en a aucune), l'article est marqué **« non vérifié »**.
- Il n'y a plus d'appel de vérification par le modèle, ni de correction.

Limite à connaître : ce contrôle prouve que la citation figure dans l'article. Il ne prouve pas que la citation appuie l'affirmation, ni que les explications ne disent rien au-delà des affirmations listées. Le badge « vérifié » signifie donc « citations retrouvées dans l'article ».

## Figures

Les cartes et la vue profondeur montrent des figures de l'article, choisies sans appel de modèle supplémentaire.

### Extraction (pipeline, gratuite)

- Depuis la version HTML d'arXiv : chaque figure de premier niveau, avec son label tel qu'imprimé (« 1 », « S1 »), les adresses de toutes ses images (sous-figures comprises, PNG ou SVG) et sa légende complète, équations conservées en LaTeX.
- Repli sans version HTML : les environnements `figure` de la source LaTeX, numérotés dans l'ordre, avec les fichiers PDF, PNG, JPG ou SVG de l'archive. Les fichiers EPS ne sont pas convertis : une figure qui n'a que de l'EPS est ignorée.
- Ignorées : les images trop petites à l'affichage (moins de 120 × 60 px, typiquement des logos), les figures sans légende réelle, les tableaux.
- Le texte complet et les figures des articles retenus sont récupérés avant la génération des cartes, en respectant le délai entre requêtes d'arXiv.

### Choix

- **La nuit**, le prompt de la carte reçoit la liste des figures (label et légende, 700 caractères au plus par légende) et rend le label de la figure qui montre le mieux le résultat principal, ou rien.
- **À l'ouverture**, le prompt du détail reçoit la même liste et choisit une à trois figures, avec pour chacune une phrase « what to look at ». Les explications peuvent y renvoyer (« Fig. 2 »).
- Un label qui n'existe pas dans la liste extraite est ignoré ; au plus une figure pour la carte, trois pour le détail. Cette validation est la même dans le pipeline (`figures.py`) et dans l'Edge Function (`figures.ts`), testée sur des cas partagés.

### Stockage

- Table `paper_figures` : toutes les figures des articles de l'édition y sont décrites (label, position, légende, adresses d'origine). Les figures choisies reçoivent un rôle (`card`, `detail`, ou les deux) et, pour le détail, leur phrase « what to look at ».
- **Seules les figures choisies sont copiées** dans le compartiment privé `figures` de Supabase Storage, converties en WebP, 1400 px de large au plus.
- La figure d'une carte est copiée la nuit même. Les figures choisies à l'ouverture par l'Edge Function sont copiées par le pipeline de nuit suivant (`sync-figures`) : la fonction ne fait pas de traitement d'image. En attendant, l'app les affiche depuis leur adresse d'origine sur arXiv.

### Dans l'app

- La figure de la carte en haut de la carte ; dans la vue profondeur, chaque figure avec sa phrase « what to look at » et sa légende (LaTeX rendu par KaTeX).
- Un appui ouvre la figure en plein écran, avec zoom.
- Les images sont mises en cache sur le téléphone sous une clé stable ; celles des cartes sont chargées dès l'accueil de l'édition.

## Coût

- **Plafond mensuel** (`budget.monthly_usd`, 15 $ par défaut), nuit et ouvertures confondues.
- La nuit : le budget restant est réparti sur les jours restants du mois et le nombre de cartes est fixé avant tout appel payant ; une édition n'est jamais coupée en cours de route.
- À l'ouverture : le détail est refusé si son coût estimé ferait dépasser le plafond.
- Chaque appel est journalisé (tokens, coût) ; table `api_usage` en base.
- Les mesures de coût sont dans `comparison/`.

## Conséquences sur le modèle de données (section 9 du doc)

- Nouvelle table `paper_figures` et compartiment de stockage privé `figures` (voir Figures).
- La carte porte le label de sa figure (`card.figure`) ; le détail porte ses figures (`detail.figures`).

- `contents` est scindé : `cards` (paper_id, carte JSON, modèle, version du prompt, date) et `details` (paper_id, détail JSON, affirmations retirées, statut de vérification, source et mode du texte, modèle, version du prompt, date).
- `papers.texte complet` est rempli la nuit pour les articles de l'édition.
- Le badge « vérifié » de la carte n'existe plus à ce stade : il apparaît dans la vue profondeur, une fois le détail généré.
- Nouvelle Edge Function `open-paper`, à côté de `ask-paper`.

## Ordre de construction

1. Pipeline local en ligne de commande — fait (`run`, `open`, `compare`).
2. Schéma Supabase, écriture du pipeline dans la base, Edge Function `open-paper` — fait et vérifié sur le vrai projet (`docs/SUPABASE.md`).
3. Workflows GitHub Actions (pipeline de nuit, notifications) — écrits et testés (`docs/GITHUB_ACTIONS.md`) ; l'envoi réel d'une notification attend l'app.
4. App Android : flux Aujourd'hui avec état de chargement du détail — fait, vérifié dans un navigateur et sur téléphone avec Expo Go (`docs/APP.md`) ; puis réglages, puis notifications, puis build APK.
5. Ensuite seulement, V2 puis V3.
