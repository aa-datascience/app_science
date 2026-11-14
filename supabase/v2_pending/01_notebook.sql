-- V2 (d) — Carnet : articles sauvegardés, notes, tags, recherche.
-- NON APPLIQUÉE. À exécuter seulement après validation de docs/V2_PLAN.md.

create table notebook (
  paper_id    text primary key references papers on delete cascade,
  note        text not null default '',
  tags        text[] not null default '{}',
  saved_at    timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index notebook_tags on notebook using gin (tags);

alter table notebook enable row level security;
create policy owner_read   on notebook for select to authenticated using (is_owner());
create policy owner_insert on notebook for insert to authenticated with check (is_owner());
create policy owner_update on notebook for update to authenticated using (is_owner()) with check (is_owner());
create policy owner_delete on notebook for delete to authenticated using (is_owner());

-- Tout ce que l'écran Carnet affiche et exporte (Markdown, BibTeX), en une lecture.
create view notebook_entries with (security_invoker = true) as
select
  n.paper_id,
  n.note,
  n.tags,
  n.saved_at,
  n.updated_at,
  p.title,
  p.authors,
  p.categories,
  p.primary_category,
  p.published,
  c.card ->> 'plain_title' as plain_title,
  c.card ->> 'finding'     as finding,
  -- Texte de recherche : note, tags, titres, auteurs.
  to_tsvector(
    'english',
    coalesce(n.note, '') || ' ' || array_to_string(n.tags, ' ') || ' ' || p.title || ' ' ||
    coalesce(c.card ->> 'plain_title', '') || ' ' || array_to_string(p.authors, ' ')
  ) as search
from notebook n
join papers p on p.arxiv_id = n.paper_id
left join cards c on c.paper_id = n.paper_id;

-- Recherche plein texte du carnet. Chaîne vide : tout le carnet, le plus récent d'abord.
create function search_notebook(q text default '')
returns setof notebook_entries
language sql stable security invoker set search_path = public
as $$
  select *
  from notebook_entries e
  where q = '' or e.search @@ websearch_to_tsquery('english', q)
  order by e.saved_at desc
$$;

-- Les articles déjà marqués « saved » en V1 entrent dans le carnet.
insert into notebook (paper_id, saved_at)
select paper_id, min(created_at) from feedback where type = 'saved' group by paper_id
on conflict (paper_id) do nothing;
