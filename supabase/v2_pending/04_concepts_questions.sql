-- V2 (b) — Fiches concepts (réutilisées entre articles) et questions de compréhension.
-- NON APPLIQUÉE. À exécuter seulement après validation de docs/V2_PLAN.md.
--
-- Concepts et questions sont produits par le MÊME appel que les explications, à l'ouverture
-- (Edge Function open-paper) : pas d'appel supplémentaire. Tout est écrit par la clé de service.

create table concepts (
  id                 text primary key,           -- identifiant stable, ex. « andreev-bound-state »
  name               text not null,
  simple_definition  text not null,
  expert_definition  text not null,              -- LaTeX en $...$
  primary_category   text not null default '',   -- catégorie de l'article qui l'a créé : sert à borner la liste donnée au modèle
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
  unique (paper_id, position)
);

-- Réponses données dans l'app (écrites par l'app, hors ligne compris).
create table question_attempts (
  id           bigint generated always as identity primary key,
  question_id  bigint not null references questions on delete cascade,
  answer       text not null,
  correct      boolean,                          -- null pour une réponse courte, que l'on ne corrige pas automatiquement
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
