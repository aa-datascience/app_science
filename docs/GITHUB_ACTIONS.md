# Pipeline de nuit et notifications (GitHub Actions)

Trois workflows, dans `.github/workflows/` :

| Workflow | Quand | Ce qu'il fait |
| --- | --- | --- |
| `nightly.yml` | 04:20 et 05:20 UTC, chaque jour | Construit l'édition (classement + cartes) et l'écrit dans Supabase |
| `notify.yml` | 05:35, 06:35, 18:05 et 19:05 UTC | Envoie la notification du matin ou le rappel du soir si elle est due |
| `tests.yml` | À chaque push | Lance les tests ; aucun secret, aucune dépense |

## Secrets à ajouter une fois

Dans le dépôt GitHub : **Settings → Secrets and variables → Actions → New repository secret**, avec les mêmes valeurs que dans `.env` :

- `ANTHROPIC_API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`

Tant qu'ils manquent, les workflows planifiés échouent sans rien dépenser (GitHub envoie un e-mail d'échec).

## Édition de nuit

arXiv met ses flux à jour à minuit, heure de la côte Est (5 h UTC). Le pipeline est lancé deux fois et se protège lui-même :

- une édition déjà prête n'est jamais refaite (`--force` pour l'imposer) ;
- si le flux contient encore l'annonce de la veille, le premier lancement ne fait rien (`--stale wait`) ;
- au dernier lancement, un flux toujours pas à jour (week-end, jour sans annonce) donne une édition tirée de la réserve de la semaine (`--stale reserve`) ;
- les cartes passent par l'API Batches ; si le lot échoue ou dépasse le délai (`batch.timeout_minutes`), elles sont refaites en appels directs.

Coût mesuré : environ 2 centimes par nuit. Le plafond mensuel de `config.yaml` s'applique.

Pour lancer une édition à la main : onglet **Actions → Édition de nuit → Run workflow**.

## Notifications

Une le matin (« Today's edition is ready — 8 papers »), un rappel le soir seulement si l'édition n'est pas terminée, et rien d'autre. Chaque envoi est noté dans `editions.morning_notified_at` / `evening_notified_at`, donc jamais répété.

- Heures par défaut : 7 h 30 et 20 h, Europe/Zurich ; réglables dans `profile.settings` (`morning_time`, `evening_time`, `timezone`). GitHub ne connaissant que l'heure UTC, chaque notification a deux créneaux (été et hiver) et une heure réglée est arrondie au créneau suivant.
- L'envoi passe par le service de push d'Expo, vers `profile.push_token`. **Tant que l'app n'a pas enregistré ce jeton, rien n'est envoyé** : la commande le dit et s'arrête.
- Essai sans envoi : `.venv/Scripts/python -m arxiv_digest notify morning --dry-run`.

## Limites connues

- Les crons de GitHub peuvent partir avec plusieurs minutes de retard, parfois davantage.
- GitHub désactive les workflows planifiés d'un dépôt resté 60 jours sans activité ; il suffit de les réactiver dans l'onglet Actions.
- L'envoi réel d'une notification n'a jamais été testé : il faut l'app et un jeton Expo.
