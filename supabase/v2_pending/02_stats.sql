-- V2 (e) — Statistiques de lecture et bilan de la semaine. Tout en SQL, sans modèle.
-- NON APPLIQUÉE. À exécuter seulement après validation de docs/V2_PLAN.md.
--
-- Définitions (spec §8) :
--   montré  : la carte est apparue à l'écran          (reading_events.event = 'shown')
--   lu      : la vue profondeur a été ouverte         (reading_events.event = 'opened')
--   ignoré  : montré sans être lu
--   édition terminée : editions.completed_at renseigné
-- Une semaine va du lundi au dimanche. Pas de compteur de jours consécutifs.

-- Une ligne par article d'édition, avec ce que le lecteur en a fait.
create view reading_log with (security_invoker = true) as
select
  i.edition_date,
  date_trunc('week', i.edition_date::timestamp)::date as week,   -- lundi de la semaine
  i.paper_id,
  i.slot,
  p.primary_category,
  exists (select 1 from reading_events e where e.paper_id = i.paper_id and e.edition_date = i.edition_date and e.event = 'shown')  as shown,
  exists (select 1 from reading_events e where e.paper_id = i.paper_id and e.edition_date = i.edition_date and e.event = 'opened') as read,
  exists (select 1 from feedback f where f.paper_id = i.paper_id and f.type = 'saved') as saved
from edition_items i
join papers p on p.arxiv_id = i.paper_id;

-- Statistiques des `weeks` dernières semaines (4 à 12), semaine en cours comprise.
create function get_stats(weeks int default 4)
returns jsonb
language sql stable security invoker set search_path = public
as $$
  with bounds as (
    select date_trunc('week', now())::date - (greatest(1, least(weeks, 52)) - 1) * 7 as first_week
  ),
  log as (select l.* from reading_log l, bounds b where l.week >= b.first_week),
  by_week as (
    select
      week,
      count(*) filter (where shown)              as shown,
      count(*) filter (where read)               as read,
      count(*) filter (where shown and not read) as skipped,
      count(*) filter (where saved)              as saved
    from log group by week
  ),
  done as (
    select date_trunc('week', e.date::timestamp)::date as week, count(*) as editions_completed
    from editions e, bounds b
    where e.completed_at is not null and e.date >= b.first_week
    group by 1
  ),
  by_category as (
    select
      primary_category,
      count(*) filter (where shown) as shown,
      count(*) filter (where read)  as read
    from log group by primary_category
  )
  select jsonb_build_object(
    'weeks', coalesce((
      select jsonb_agg(jsonb_build_object(
        'week', w.week,
        'shown', w.shown,
        'read', w.read,
        'skipped', w.skipped,
        'saved', w.saved,
        'read_rate', case when w.shown > 0 then round(w.read::numeric / w.shown, 3) end,
        'editions_completed', coalesce(d.editions_completed, 0)
      ) order by w.week)
      from by_week w left join done d using (week)
    ), '[]'::jsonb),
    'categories', coalesce((
      select jsonb_agg(jsonb_build_object(
        'category', c.primary_category,
        'shown', c.shown,
        'read', c.read,
        'read_rate', case when c.shown > 0 then round(c.read::numeric / c.shown, 3) end
      ) order by c.shown desc)
      from by_category c where c.shown > 0
    ), '[]'::jsonb)
  )
$$;

-- Bilan de la semaine passée (lundi à dimanche précédents), affiché en tête de l'édition du lundi.
create function last_week_summary()
returns jsonb
language sql stable security invoker set search_path = public
as $$
  with w as (select date_trunc('week', now())::date - 7 as week)
  select jsonb_build_object(
    'week', w.week,
    'shown',   (select count(*) from reading_log l where l.week = w.week and l.shown),
    'read',    (select count(*) from reading_log l where l.week = w.week and l.read),
    'skipped', (select count(*) from reading_log l where l.week = w.week and l.shown and not l.read),
    'saved',   (select count(*) from reading_log l where l.week = w.week and l.saved),
    'editions_completed', (
      select count(*) from editions e
      where e.completed_at is not null and e.date >= w.week and e.date < w.week + 7
    ),
    'most_read_category', (
      select l.primary_category from reading_log l
      where l.week = w.week and l.read group by 1 order by count(*) desc, 1 limit 1
    ),
    'most_skipped_category', (
      select l.primary_category from reading_log l
      where l.week = w.week and l.shown and not l.read group by 1 order by count(*) desc, 1 limit 1
    )
  )
  from w
$$;
