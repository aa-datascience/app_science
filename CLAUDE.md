# App de veille arXiv

Édition quotidienne d'articles de physique tirés d'arXiv, expliqués et vérifiés. La spec complète est dans `docs/SPEC.md` : la lire avant tout changement de périmètre.

## Structure

- `pipeline/` — Python 3.12, paquet `arxiv_digest` (la nuit : ingestion, présélection, classement, cartes ; à l'ouverture : détail et vérification des citations sans modèle).
- `prompts/` — prompts versionnés (la version enregistrée est l'empreinte du fichier).
- `config.yaml` — réglages (catégories, modèles, poids, plafond de dépense). Secrets dans `.env`, jamais commités.
- `out/` — sorties locales, non commitées.
- À venir : `supabase/`, `.github/workflows/`, `app/` (ordre de construction : spec §12).

## Commandes (depuis `pipeline/`)

- Tests : `.venv/Scripts/python -m pytest -q`
- Essai gratuit : `.venv/Scripts/python -m arxiv_digest run --no-llm`
- Édition du jour, cartes seulement (payant) : `.venv/Scripts/python -m arxiv_digest run` ou `run --batch` (API Batches, pipeline de nuit)
- Ouverture simulée d'un article (payant) : `.venv/Scripts/python -m arxiv_digest open <arxiv_id>`
- Essai de coût et de qualité (payant, plafonné par `--max-usd`) : `.venv/Scripts/python -m arxiv_digest compare` → `comparison/AAAA-MM-JJ.md`

## Règles

- Demander avant toute dépense ou tout choix d'hébergement. Lancer le pipeline sans `--no-llm` est une dépense.
- Ne pas changer les modèles par défaut de `config.yaml` sans décision explicite.
- Plafond mensuel (`budget.monthly_usd`) : la taille de l'édition est fixée avant tout appel payant (`budget.py`) ; une édition n'est jamais coupée en cours de route.
- La clé API vit dans `.env` uniquement. Ne jamais commiter `.env`, ne jamais mettre de clé dans `.env.example`.
- Aucun appel réel à l'API Claude dans les tests.
- Sorties des modèles validées par des schémas Pydantic (`models.py`).
- Contenu généré en anglais ; code commenté et documentation en français.
- arXiv : garder le délai entre requêtes et le User-Agent de `config.yaml`.
