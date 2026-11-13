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

L'édition est écrite dans `out/editions/AAAA-MM-JJ.json` et chaque appel au modèle dans `out/api_usage.jsonl` (tokens, coût estimé). Le pipeline s'arrête proprement au plafond `budget.daily_usd` de `config.yaml`.

## Réglages

Tout est dans `config.yaml` : catégories suivies, mots-clés, description des intérêts, modèles, pondération du score, plafond de dépense. Les prompts sont dans `prompts/`.

## Tests

```bash
.venv/Scripts/python -m pytest -q
```
