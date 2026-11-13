# App de veille arXiv

Édition quotidienne d'articles de physique tirés d'arXiv, expliqués et vérifiés. La spec complète est dans `docs/SPEC.md` : la lire avant tout changement de périmètre.

## Structure

- `pipeline/` — Python 3.12, paquet `arxiv_digest` (ingestion, présélection, classement, texte complet, génération, vérification).
- `prompts/` — prompts versionnés (la version enregistrée est l'empreinte du fichier).
- `config.yaml` — réglages (catégories, modèles, poids, plafond de dépense). Secrets dans `.env`, jamais commités.
- `out/` — sorties locales, non commitées.
- À venir : `supabase/`, `.github/workflows/`, `app/` (ordre de construction : spec §12).

## Commandes (depuis `pipeline/`)

- Tests : `.venv/Scripts/python -m pytest -q`
- Essai gratuit : `.venv/Scripts/python -m arxiv_digest run --no-llm`
- Pipeline complet (payant) : `.venv/Scripts/python -m arxiv_digest run`

## Règles

- Demander avant toute dépense ou tout choix d'hébergement. Lancer le pipeline sans `--no-llm` est une dépense.
- Aucun appel réel à l'API Claude dans les tests.
- Sorties des modèles validées par des schémas Pydantic (`models.py`).
- Contenu généré en anglais ; code commenté et documentation en français.
- arXiv : garder le délai entre requêtes et le User-Agent de `config.yaml`.
