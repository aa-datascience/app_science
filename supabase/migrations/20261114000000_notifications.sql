-- Notifications : on note quand chacune a été envoyée, pour ne jamais l'envoyer deux fois.
-- Écrit par le pipeline (clé de service) ; l'app ne peut toujours modifier que completed_at.

alter table editions
  add column morning_notified_at timestamptz,
  add column evening_notified_at timestamptz;
