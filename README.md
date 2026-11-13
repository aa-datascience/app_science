# App de veille arXiv

Une édition quotidienne d'articles de physique tirés d'arXiv, transformés en contenu clair et vérifié. Spec : [docs/SPEC.md](docs/SPEC.md).

État : étape 1 de la spec (§12) — le pipeline tourne en local et écrit l'édition en JSON.

## Installation

```bash
cd pipeline
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Utilisation

Essai gratuit (ingestion et présélection, aucun appel à l'API Claude) :

```bash
.venv/Scripts/python -m arxiv_digest run --no-llm
```

Pipeline complet : copier `.env.example` vers `.env`, y mettre la clé API Anthropic, puis :

```bash
.venv/Scripts/python -m arxiv_digest run --size 2
```

L'édition est écrite dans `out/editions/AAAA-MM-JJ.json` et chaque appel au modèle dans `out/api_usage.jsonl` (tokens, coût).

Pour le pipeline de nuit, `run --batch` passe la génération et la vérification par l'API Message Batches : moitié prix, résultat en général en moins d'une heure.

## Coût

- **Plafond mensuel** (`budget.monthly_usd`, 15 $ par défaut) : le budget restant est réparti sur les jours restants du mois. Si le budget du jour ne couvre pas l'édition complète, le nombre d'articles est réduit avant de commencer et c'est signalé dans les logs et dans les notes de l'édition.
- **Cache** (`cache`) : le texte de l'article est mis en cache entre génération, vérification et corrections.
- **Sections utiles** (`fulltext.mode: sections`) : n'envoie que résumé, introduction, résultats et discussion/conclusion ; pour les articles sans section « Results », retire seulement annexes, méthodes et compléments.

## Essai comparatif des modèles

```bash
.venv/Scripts/python -m arxiv_digest compare --n 4 --max-usd 5
```

Génère et vérifie les mêmes articles avec Haiku, Sonnet et Opus, et écrit `comparison/AAAA-MM-JJ.md` : contenus côte à côte, résultat de la vérification, coûts mesurés et extrapolation mensuelle.

## Réglages

Tout est dans `config.yaml` : catégories suivies, mots-clés, description des intérêts, modèles, pondération du score, plafond de dépense. Les prompts sont dans `prompts/`.

## Tests

```bash
.venv/Scripts/python -m pytest -q
```
