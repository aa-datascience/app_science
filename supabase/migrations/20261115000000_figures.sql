-- Figures des articles.
--
-- Toutes les figures d'un article de l'édition sont décrites ici (label, légende, adresses d'origine),
-- pour que les modèles puissent choisir. Seules les figures choisies reçoivent un rôle, et seules
-- celles-là sont copiées dans Supabase Storage (WebP, 1400 px de large au plus).

create table paper_figures (
  paper_id         text not null references papers on delete cascade,
  label            text not null,                -- « 1 », « 2 », « S1 »… tel qu'imprimé dans l'article
  position         int  not null default 0,      -- ordre dans l'article
  caption          text not null,                -- légende complète, LaTeX conservé
  sources          jsonb not null default '[]',  -- adresses d'origine des images (sous-figures comprises)
  roles            text[] not null default '{}' check (roles <@ array['card', 'detail']),
  what_to_look_at  text,                         -- phrase écrite à l'ouverture, pour la vue profondeur
  storage_paths    jsonb not null default '[]',  -- chemins dans le compartiment « figures », une fois copiées
  stored           boolean not null default false,
  created_at       timestamptz not null default now(),
  primary key (paper_id, label)
);
create index paper_figures_pending on paper_figures (stored) where roles <> '{}';

alter table paper_figures enable row level security;
create policy owner_read on paper_figures for select to authenticated using (is_owner());

-- Compartiment privé : l'app y accède par des adresses signées, avec la session du propriétaire.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('figures', 'figures', false, 2097152, array['image/webp'])
on conflict (id) do nothing;

create policy figures_owner_read on storage.objects
  for select to authenticated
  using (bucket_id = 'figures' and public.is_owner());
