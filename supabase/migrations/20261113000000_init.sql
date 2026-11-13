-- Schéma V1 : édition quotidienne (cartes), détail à l'ouverture, feedback, coûts.
-- Les tables V2/V3 de la spec (concepts, carnet, questions à l'article, dossiers) viendront avec leurs fonctionnalités.
--
-- Accès : le pipeline de nuit et l'Edge Function utilisent la clé de service, qui contourne RLS.
-- L'app utilise la clé publique et la session d'UN compte, celui inscrit dans app_owner.

-- ---------------------------------------------------------------- propriétaire

create table app_owner (
  user_id uuid primary key
);
comment on table app_owner is 'Le seul compte autorisé à lire et écrire depuis l''app. Une ligne, insérée à la main.';

alter table app_owner enable row level security;  -- aucune policy : illisible depuis l'app

create function is_owner() returns boolean
  language sql stable security definer set search_path = public
  as $$ select exists (select 1 from app_owner where user_id = auth.uid()) $$;

-- ---------------------------------------------------------------- articles

create table papers (
  arxiv_id          text primary key,
  version           int  not null default 1,
  title             text not null,
  authors           text[] not null default '{}',
  abstract          text not null,
  categories        text[] not null default '{}',
  primary_category  text not null default '',
  published         text not null default '',
  -- Texte envoyé au modèle à l'ouverture, rempli la nuit pour les articles de l'édition.
  full_text         text,
  text_source       text check (text_source in ('html', 'latex', 'pdf', 'abstract')),
  text_mode         text check (text_mode in ('full', 'sections')),
  text_truncated    boolean not null default false,
  created_at        timestamptz not null default now()
);

create table rankings (
  paper_id         text not null references papers on delete cascade,
  date             date not null,
  slot             text not null check (slot in ('main', 'exploration')),
  prefilter_score  real not null,
  relevance        int  not null,
  importance       int  not null,
  novelty          int  not null,
  difficulty       int  not null,
  why              text not null,
  final_score      real not null,
  model            text not null,
  prompt_version   text not null,
  primary key (paper_id, date)
);
create index rankings_date on rankings (date);

-- ---------------------------------------------------------------- éditions

create table editions (
  date          date primary key,
  status        text not null check (status in ('pending', 'ready', 'failed', 'fallback')),
  ready_at      timestamptz,
  completed_at  timestamptz,           -- fin de lecture, écrite par l'app
  cost_usd      numeric(10, 4) not null default 0,
  notes         text[] not null default '{}'
);

create table edition_items (
  edition_date  date not null references editions on delete cascade,
  paper_id      text not null references papers,
  position      int  not null,
  slot          text not null check (slot in ('main', 'exploration')),
  primary key (edition_date, paper_id),
  unique (edition_date, position)
);
create index edition_items_paper on edition_items (paper_id);

-- Carte : générée la nuit à partir du titre et du résumé.
create table cards (
  paper_id        text primary key references papers on delete cascade,
  card            jsonb not null,
  model           text not null,
  prompt_version  text not null,
  created_at      timestamptz not null default now()
);

-- Détail : généré à la première ouverture par l'Edge Function open-paper, jamais régénéré.
create table details (
  paper_id             text primary key references papers on delete cascade,
  detail               jsonb not null,               -- explications, contexte, affirmations dont la citation est retrouvée
  removed_claims       jsonb not null default '[]',  -- affirmations retirées (citation introuvable)
  verification_status  text not null check (verification_status in ('verified', 'unverified')),
  text_source          text not null,
  based_on_abstract    boolean not null,
  text_truncated       boolean not null default false,
  text_mode            text not null default 'full',
  model                text not null,
  prompt_version       text not null,
  created_at           timestamptz not null default now()
);

-- ---------------------------------------------------------------- lecture

create table feedback (
  id          bigint generated always as identity primary key,
  paper_id    text not null references papers on delete cascade,
  type        text not null check (type in ('interesting', 'not_interesting', 'too_easy', 'too_hard', 'saved')),
  created_at  timestamptz not null default now()
);
create index feedback_paper on feedback (paper_id);

create table reading_events (
  id            bigint generated always as identity primary key,
  paper_id      text references papers on delete cascade,
  edition_date  date references editions on delete cascade,
  event         text not null check (event in ('shown', 'opened', 'section_viewed', 'question_asked', 'edition_completed')),
  section       text,
  created_at    timestamptz not null default now()
);
create index reading_events_date on reading_events (edition_date);

-- ---------------------------------------------------------------- réglages et coûts

-- Réglages de l'app (nombre d'articles, heures des notifications, fuseau) et jeton de push.
create table profile (
  id          int primary key default 1 check (id = 1),
  settings    jsonb not null default '{}',
  push_token  text,
  updated_at  timestamptz not null default now()
);
insert into profile (id) values (1);

-- Copie de ce dont l'Edge Function a besoin (modèle du détail, prix, plafond, prompts, schéma
-- de sortie), réécrite chaque nuit par le pipeline à partir de config.yaml et de prompts/ :
-- une seule source de vérité, dans le dépôt.
create table server_config (
  id          int primary key default 1 check (id = 1),
  config      jsonb not null,
  updated_at  timestamptz not null default now()
);

create table api_usage (
  id                     bigint generated always as identity primary key,
  date                   date not null,
  step                   text not null,
  model                  text not null,
  batch                  boolean not null default false,
  arxiv_id               text,
  mode                   text,
  label                  text,
  input_tokens           int not null default 0,
  cache_write_5m_tokens  int not null default 0,
  cache_write_1h_tokens  int not null default 0,
  cache_read_tokens      int not null default 0,
  output_tokens          int not null default 0,
  cost_usd               numeric(12, 6) not null default 0,
  created_at             timestamptz not null default now()
);
create index api_usage_date on api_usage (date);

-- ---------------------------------------------------------------- vue de l'édition

-- La dernière édition prête, cartes dans l'ordre. security_invoker : RLS s'applique au lecteur.
create view edition_today with (security_invoker = true) as
select
  e.date,
  e.status,
  e.completed_at,
  i.position,
  i.slot,
  p.arxiv_id,
  p.title,
  p.authors,
  p.categories,
  c.card,
  r.why,
  (d.paper_id is not null) as has_detail
from editions e
join edition_items i on i.edition_date = e.date
join papers p on p.arxiv_id = i.paper_id
join cards c on c.paper_id = p.arxiv_id
left join rankings r on r.paper_id = p.arxiv_id and r.date = e.date
left join details d on d.paper_id = p.arxiv_id
where e.date = (select max(date) from editions where status in ('ready', 'fallback'))
order by i.position;

-- ---------------------------------------------------------------- sécurité (RLS)

alter table papers          enable row level security;
alter table rankings        enable row level security;
alter table editions        enable row level security;
alter table edition_items   enable row level security;
alter table cards           enable row level security;
alter table details         enable row level security;
alter table feedback        enable row level security;
alter table reading_events  enable row level security;
alter table profile         enable row level security;
alter table server_config   enable row level security;  -- aucune policy : réservée à la clé de service
alter table api_usage       enable row level security;

-- Lecture : le propriétaire seulement.
create policy owner_read on papers         for select to authenticated using (is_owner());
create policy owner_read on rankings       for select to authenticated using (is_owner());
create policy owner_read on editions       for select to authenticated using (is_owner());
create policy owner_read on edition_items  for select to authenticated using (is_owner());
create policy owner_read on cards          for select to authenticated using (is_owner());
create policy owner_read on details        for select to authenticated using (is_owner());
create policy owner_read on feedback       for select to authenticated using (is_owner());
create policy owner_read on reading_events for select to authenticated using (is_owner());
create policy owner_read on profile        for select to authenticated using (is_owner());
create policy owner_read on api_usage      for select to authenticated using (is_owner());

-- Écriture depuis l'app : feedback, événements de lecture, réglages, fin de lecture d'une édition.
create policy owner_insert on feedback       for insert to authenticated with check (is_owner());
create policy owner_delete on feedback       for delete to authenticated using (is_owner());
create policy owner_insert on reading_events for insert to authenticated with check (is_owner());
create policy owner_update on profile        for update to authenticated using (is_owner()) with check (is_owner());
create policy owner_update on editions       for update to authenticated using (is_owner()) with check (is_owner());

-- L'app ne peut modifier que completed_at sur une édition.
revoke update on editions from authenticated;
grant update (completed_at) on editions to authenticated;

revoke all on app_owner, server_config from anon, authenticated;
