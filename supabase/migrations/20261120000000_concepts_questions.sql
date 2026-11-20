-- V2, étape 4 — Fiches concepts (réutilisées entre articles) et questions de compréhension.
--
-- Concepts et questions sont produits par le MÊME appel que les explications, à l'ouverture
-- (Edge Function open-paper) : pas d'appel supplémentaire. Ils sont écrits par la clé de service ;
-- l'app n'écrit que les réponses aux questions, et fusionne deux concepts par merge_concepts().

create table concepts (
  id                 text primary key,           -- identifiant stable, ex. « andreev-bound-state »
  name               text not null,
  simple_definition  text not null,
  expert_definition  text not null,              -- LaTeX en $...$
  primary_category   text not null default '',   -- catégorie de l'article qui l'a créé : sert à ordonner la liste donnée au modèle
  first_paper_id     text references papers on delete set null,
  created_at         timestamptz not null default now()
);

-- Concepts liés : paire non ordonnée, stockée une fois (a < b).
create table concept_links (
  a  text not null references concepts on delete cascade,
  b  text not null references concepts on delete cascade,
  primary key (a, b),
  check (a < b)
);

create table paper_concepts (
  paper_id    text not null references papers on delete cascade,
  concept_id  text not null references concepts on delete cascade,
  position    int  not null default 0,
  primary key (paper_id, concept_id)
);
create index paper_concepts_concept on paper_concepts (concept_id);

create table questions (
  id           bigint generated always as identity primary key,
  paper_id     text not null references papers on delete cascade,
  position     int  not null,
  kind         text not null check (kind in ('mcq', 'short')),
  prompt       text not null,
  options      jsonb not null default '[]',      -- choix d'un QCM ; vide pour une réponse courte
  answer       text not null,                    -- un QCM : le texte exact de la bonne option
  explanation  text not null,
  quote        text not null,                    -- passage de l'article qui fonde la réponse, retrouvé dans le texte
  created_at   timestamptz not null default now(),
  -- Un détail régénéré archive ses anciennes questions au lieu de les supprimer :
  -- l'historique des réponses est conservé (décision 7 de docs/V2_PLAN.md).
  archived_at  timestamptz
);
create unique index questions_current on questions (paper_id, position) where archived_at is null;

-- Réponses données dans l'app (écrites par l'app, hors ligne compris).
-- QCM : `answer` est l'option choisie, `correct` calculé par l'app.
-- Réponse courte : pas de correction automatique ; le lecteur dit lui-même s'il avait bon.
create table question_attempts (
  id           bigint generated always as identity primary key,
  question_id  bigint not null references questions on delete cascade,
  answer       text not null default '',
  correct      boolean,
  created_at   timestamptz not null default now()
);
create index question_attempts_question on question_attempts (question_id);

alter table concepts          enable row level security;
alter table concept_links     enable row level security;
alter table paper_concepts    enable row level security;
alter table questions         enable row level security;
alter table question_attempts enable row level security;

create policy owner_read on concepts          for select to authenticated using (is_owner());
create policy owner_read on concept_links     for select to authenticated using (is_owner());
create policy owner_read on paper_concepts    for select to authenticated using (is_owner());
create policy owner_read on questions         for select to authenticated using (is_owner());
create policy owner_read on question_attempts for select to authenticated using (is_owner());
create policy owner_insert on question_attempts for insert to authenticated with check (is_owner());

-- Fiche d'un concept avec les articles où il apparaît, pour l'écran Concepts.
create view concept_cards with (security_invoker = true) as
select
  c.*,
  (select count(*) from paper_concepts pc where pc.concept_id = c.id) as paper_count,
  (select coalesce(jsonb_agg(jsonb_build_object('paper_id', pc.paper_id, 'title', p.title) order by p.created_at desc), '[]'::jsonb)
     from paper_concepts pc join papers p on p.arxiv_id = pc.paper_id where pc.concept_id = c.id) as papers,
  (select coalesce(jsonb_agg(case when l.a = c.id then l.b else l.a end), '[]'::jsonb)
     from concept_links l where c.id in (l.a, l.b)) as related
from concepts c;

-- Fusion de deux fiches en doublon, depuis l'écran Concepts (décision 5) : `dup` disparaît,
-- ses articles et ses liens passent à `keep`. Réservé au propriétaire.
create function merge_concepts(dup text, keep text)
returns void
language plpgsql security definer set search_path = public
as $$
begin
  if not is_owner() then raise exception 'forbidden'; end if;
  if dup = keep then return; end if;
  if not exists (select 1 from concepts where id = dup) or not exists (select 1 from concepts where id = keep) then
    raise exception 'unknown concept';
  end if;
  insert into paper_concepts (paper_id, concept_id, position)
    select paper_id, keep, position from paper_concepts where concept_id = dup
    on conflict do nothing;
  insert into concept_links (a, b)
    select least(keep, o), greatest(keep, o)
    from (select case when a = dup then b else a end as o from concept_links where dup in (a, b)) x
    where o <> keep
    on conflict do nothing;
  -- La fiche gardée prend la date et l'article de création les plus anciens.
  update concepts k set
    created_at = least(k.created_at, d.created_at),
    first_paper_id = case when d.created_at < k.created_at then coalesce(d.first_paper_id, k.first_paper_id) else k.first_paper_id end
  from concepts d where k.id = keep and d.id = dup;
  -- Les lignes restantes de `dup` partent avec lui (on delete cascade).
  delete from concepts where id = dup;
end
$$;
revoke execute on function merge_concepts(text, text) from public, anon;
grant execute on function merge_concepts(text, text) to authenticated;

-- Statistiques : get_stats reçoit, par semaine, les questions réussies et les nouveaux concepts (spec §8).
-- Une question compte une fois, à sa première réponse ; « réussie » si cette première réponse est juste.
create or replace function get_stats(weeks int default 4)
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
  first_attempts as (
    select distinct on (question_id) question_id, correct, created_at
    from question_attempts order by question_id, created_at, id
  ),
  answered as (
    select date_trunc('week', a.created_at)::date as week,
           count(*) as questions_answered,
           count(*) filter (where a.correct) as questions_correct
    from first_attempts a, bounds b where a.created_at >= b.first_week
    group by 1
  ),
  learned as (
    select date_trunc('week', c.created_at)::date as week, count(*) as new_concepts
    from concepts c, bounds b where c.created_at >= b.first_week
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
        'editions_completed', coalesce(d.editions_completed, 0),
        'questions_answered', coalesce(q.questions_answered, 0),
        'questions_correct', coalesce(q.questions_correct, 0),
        'new_concepts', coalesce(n.new_concepts, 0)
      ) order by w.week)
      from by_week w
      left join done d using (week)
      left join answered q using (week)
      left join learned n using (week)
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
