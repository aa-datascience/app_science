-- V2 (a) — Profil appris à partir des feedbacks, visible et modifiable à la main.
-- NON APPLIQUÉE. À exécuter seulement après validation de docs/V2_PLAN.md.
--
-- Aujourd'hui les poids vivent dans config.yaml. En V2 ils vivent ici : config.yaml ne sert plus
-- qu'à les initialiser. La mise à jour est faite par le pipeline (Python, sans modèle) après chaque
-- édition ; chaque changement est journalisé pour que l'écran Profil puisse l'expliquer.

create table profile_weights (
  kind        text not null check (kind in ('category', 'keyword', 'author')),
  key         text not null,                    -- « cond-mat.supr-con », « josephson », « Jane Doe »
  weight      real not null,
  -- Valeur de repos : là où le poids revient peu à peu en l'absence de feedback (anti-enfermement).
  -- Une modification à la main déplace aussi cette valeur de repos.
  baseline    real not null,
  locked      boolean not null default false,   -- verrouillé par l'utilisateur : l'apprentissage n'y touche plus
  updated_at  timestamptz not null default now(),
  primary key (kind, key)
);

-- Niveau par sous-domaine (catégorie arXiv), ajusté par « trop facile / trop dur ».
create table profile_levels (
  category    text primary key,
  level       text not null check (level in ('beginner', 'intermediate', 'expert')),
  -- Compteur signé : +1 par « trop facile », -1 par « trop dur ». Le niveau change quand il franchit un seuil.
  drift       int not null default 0,
  locked      boolean not null default false,
  updated_at  timestamptz not null default now()
);

-- Journal des changements, pour la transparence (« pourquoi ce poids a bougé »).
create table profile_changes (
  id          bigint generated always as identity primary key,
  changed_at  timestamptz not null default now(),
  source      text not null check (source in ('feedback', 'decay', 'manual', 'init')),
  kind        text not null,                    -- category | keyword | author | level
  key         text not null,
  old_value   text,
  new_value   text not null,
  reason      text                              -- ex. « 2 interesting, 1 saved le 2026-11-14 »
);
create index profile_changes_key on profile_changes (kind, key, changed_at desc);

-- Où l'apprentissage s'est arrêté : les feedbacks jusqu'à cet identifiant ont déjà été pris en compte.
alter table profile add column learned_feedback_id bigint not null default 0;
alter table profile add column learned_at timestamptz;

alter table profile_weights enable row level security;
alter table profile_levels  enable row level security;
alter table profile_changes enable row level security;

create policy owner_read on profile_weights for select to authenticated using (is_owner());
create policy owner_read on profile_levels  for select to authenticated using (is_owner());
create policy owner_read on profile_changes for select to authenticated using (is_owner());

-- L'écran Profil modifie les poids et les niveaux, et journalise ses modifications.
create policy owner_update on profile_weights for update to authenticated using (is_owner()) with check (is_owner());
create policy owner_insert on profile_weights for insert to authenticated with check (is_owner());
create policy owner_delete on profile_weights for delete to authenticated using (is_owner());
create policy owner_update on profile_levels  for update to authenticated using (is_owner()) with check (is_owner());
create policy owner_insert on profile_levels  for insert to authenticated with check (is_owner());
create policy owner_insert on profile_changes for insert to authenticated with check (is_owner() and source = 'manual');

-- L'app ne doit pas pouvoir déplacer le curseur d'apprentissage.
revoke update on profile from authenticated;
grant update (settings, push_token, updated_at) on profile to authenticated;
