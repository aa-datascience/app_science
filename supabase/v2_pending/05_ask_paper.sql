-- V2 (c) — « Demander à l'article » : conversation fondée sur le texte de l'article, citations vérifiées par script.
-- NON APPLIQUÉE. À exécuter seulement après validation de docs/V2_PLAN.md.
--
-- Écrit par l'Edge Function ask-paper (clé de service). Le texte de l'article est celui déjà stocké
-- la nuit dans papers.full_text, envoyé avec prompt caching.

create table qa_messages (
  id              bigint generated always as identity primary key,
  paper_id        text not null references papers on delete cascade,
  role            text not null check (role in ('user', 'assistant')),
  content         text not null,
  -- Réponses seulement : passages de l'article retrouvés par le script, et nombre d'affirmations retirées.
  claims          jsonb not null default '[]',       -- [{statement, quote}] dont la citation est retrouvée
  removed_claims  int not null default 0,
  not_in_paper    boolean not null default false,    -- le modèle dit que la réponse n'est pas dans l'article
  model           text,
  created_at      timestamptz not null default now()
);
create index qa_messages_paper on qa_messages (paper_id, id);

alter table qa_messages enable row level security;
create policy owner_read on qa_messages for select to authenticated using (is_owner());
-- Pas de policy d'écriture : seule l'Edge Function écrit, pour que chaque réponse passe par la vérification.
