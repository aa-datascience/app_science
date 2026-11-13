"""Où vit l'état du pipeline : fichiers locaux (out/) ou base Supabase.

Supabase est utilisé dès que SUPABASE_URL et SUPABASE_SERVICE_KEY sont définis ; c'est le cas
du pipeline de nuit sur GitHub Actions, dont le disque ne survit pas d'une nuit à l'autre.
Une copie locale de l'édition est écrite dans tous les cas.

L'accès à la base passe par l'API REST de Supabase (PostgREST) avec la clé de service.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import anthropic
import httpx

from .config import Config
from .models import Candidate, Detail, Edition, Paper, Ranked, RankItem, StoredDetail
from .steps import SOURCE_NOTES, Article, load_prompt

log = logging.getLogger(__name__)
RESERVE_DAYS = 7
PAGE = 1000


def _cutoff(day: str) -> str:
    return (date.fromisoformat(day) - timedelta(days=RESERVE_DAYS)).isoformat()


def _read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def server_config(cfg: Config) -> dict:
    """Ce dont l'Edge Function open-paper a besoin, tiré de config.yaml et de prompts/."""
    system, _ = load_prompt("system")
    detail, version = load_prompt("detail")
    return {
        "detail_model": cfg.models.generate,
        "effort": cfg.models.effort,
        "max_tokens": 16000,
        "monthly_usd": cfg.budget.monthly_usd,
        "prices": cfg.budget.prices,
        "assumed_detail_tokens": list(cfg.budget.assumed_tokens["detail"]),
        "levels": cfg.profile.levels,
        "prompts": {"system": system, "detail": detail},
        "prompt_version": version,
        "source_notes": SOURCE_NOTES,
        "detail_schema": anthropic.transform_schema(Detail),
    }


class LocalStore:
    """État dans out/ : editions/, details/, seen.json, reserve.json, api_usage.jsonl."""

    wants_fulltext = False  # en local, le texte est téléchargé à l'ouverture

    def __init__(self, out: Path):
        self.out = out

    # --- lecture ---

    def seen_ids(self) -> set[str]:
        return set(_read_json(self.out / "seen.json", []))

    def usage_rows(self, day: str) -> list[dict]:
        path = self.out / "api_usage.jsonl"
        if not path.exists():
            return []
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [r for r in rows if r["date"][:7] == day[:7]]

    def reserve(self, day: str) -> list[Ranked]:
        rows = _read_json(self.out / "reserve.json", [])
        return [Ranked.model_validate(r["ranked"]) for r in rows if r["date"] >= _cutoff(day)]

    def find_paper(self, arxiv_id: str) -> Paper | None:
        for path in sorted((self.out / "editions").glob("*.json"), reverse=True):
            for item in _read_json(path, {}).get("items", []):
                if item["paper"]["arxiv_id"] == arxiv_id:
                    return Paper.model_validate(item["paper"])
        return None

    def article(self, paper: Paper) -> Article | None:
        return None

    def get_detail(self, arxiv_id: str) -> StoredDetail | None:
        path = self.out / "details" / f"{arxiv_id}.json"
        return StoredDetail.model_validate(_read_json(path, {})) if path.exists() else None

    # --- écriture ---

    def log_usage(self, row: dict) -> None:
        path = self.out / "api_usage.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def save_night(
        self, cfg: Config, edition: Edition, ranked: list[Ranked], articles: dict[str, Article]
    ) -> None:
        day = edition.date
        _write_json(self.out / "editions" / f"{day}.json", edition.model_dump())
        used = {i.paper.arxiv_id for i in edition.items}
        _write_json(self.out / "seen.json", sorted(self.seen_ids() | used))
        rows = [
            r
            for r in _read_json(self.out / "reserve.json", [])
            if r["date"] >= _cutoff(day) and r["ranked"]["candidate"]["paper"]["arxiv_id"] not in used
        ]
        known = {r["ranked"]["candidate"]["paper"]["arxiv_id"] for r in rows}
        rows += [
            {"date": day, "ranked": r.model_dump()}
            for r in ranked
            if r.candidate.paper.arxiv_id not in used and r.candidate.paper.arxiv_id not in known
        ]
        _write_json(self.out / "reserve.json", rows)

    def save_detail(self, detail: StoredDetail) -> None:
        _write_json(self.out / "details" / f"{detail.arxiv_id}.json", detail.model_dump())


def _paper_row(p: Paper) -> dict:
    return {
        "arxiv_id": p.arxiv_id,
        "version": p.version,
        "title": p.title,
        "authors": p.authors,
        "abstract": p.abstract,
        "categories": p.categories,
        "primary_category": p.primary_category,
        "published": p.published,
    }


def _paper_from_row(row: dict) -> Paper:
    return Paper(
        arxiv_id=row["arxiv_id"],
        version=row["version"],
        title=row["title"],
        authors=row["authors"],
        abstract=row["abstract"],
        categories=row["categories"],
        published=row["published"],
    )


class SupabaseStore:
    """État dans la base Supabase ; garde aussi une copie locale de l'édition."""

    wants_fulltext = True  # l'Edge Function lit le texte en base : on le stocke la nuit

    def __init__(self, url: str, service_key: str, out: Path, client: httpx.Client | None = None):
        self.local = LocalStore(out)
        self.http = client or httpx.Client(
            base_url=url.rstrip("/") + "/rest/v1",
            headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
            timeout=60,
            transport=httpx.HTTPTransport(retries=3),
        )

    # --- PostgREST ---

    def _get(self, table: str, **params: str) -> list[dict]:
        """Toutes les lignes, par pages (PostgREST plafonne une réponse à 1000 lignes)."""
        rows: list[dict] = []
        while True:
            r = self.http.get(f"/{table}", params={**params, "limit": str(PAGE), "offset": str(len(rows))})
            r.raise_for_status()
            page = r.json()
            rows += page
            if len(page) < PAGE:
                return rows

    def _upsert(self, table: str, rows: list[dict], on_conflict: str) -> None:
        if not rows:
            return
        r = self.http.post(
            f"/{table}",
            params={"on_conflict": on_conflict},
            headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
            json=rows,
        )
        r.raise_for_status()

    # --- lecture ---

    def seen_ids(self) -> set[str]:
        return {r["paper_id"] for r in self._get("edition_items", select="paper_id")}

    def usage_rows(self, day: str) -> list[dict]:
        d = date.fromisoformat(day).replace(day=1)
        nxt = (d + timedelta(days=32)).replace(day=1)
        rows = self._get("api_usage", select="*", date=f"gte.{d.isoformat()}", **{"and": f"(date.lt.{nxt.isoformat()})"})
        return [{**r, "cost_usd": float(r["cost_usd"])} for r in rows]

    def reserve(self, day: str) -> list[Ranked]:
        rows = self._get("rankings", select="*,papers(*)", date=f"gte.{_cutoff(day)}", order="date.desc")
        out, seen = [], set()
        for r in rows:
            if r["paper_id"] in seen:
                continue
            seen.add(r["paper_id"])
            out.append(
                Ranked(
                    candidate=Candidate(paper=_paper_from_row(r["papers"]), prefilter_score=r["prefilter_score"], slot=r["slot"]),
                    rank=RankItem(
                        arxiv_id=r["paper_id"], relevance=r["relevance"], importance=r["importance"],
                        novelty=r["novelty"], difficulty=r["difficulty"], why=r["why"],
                    ),
                    final_score=r["final_score"],
                )
            )
        return out

    def _paper_row(self, arxiv_id: str) -> dict | None:
        rows = self._get("papers", select="*", arxiv_id=f"eq.{arxiv_id}")
        return rows[0] if rows else None

    def find_paper(self, arxiv_id: str) -> Paper | None:
        row = self._paper_row(arxiv_id)
        return _paper_from_row(row) if row else None

    def article(self, paper: Paper) -> Article | None:
        """Le texte stocké la nuit, tel qu'il sera envoyé au modèle."""
        row = self._paper_row(paper.arxiv_id)
        if not row or not row.get("full_text"):
            return None
        return Article(paper, row["full_text"], row["text_source"], row["text_truncated"], row["text_mode"])

    def get_detail(self, arxiv_id: str) -> StoredDetail | None:
        rows = self._get("details", select="*", paper_id=f"eq.{arxiv_id}")
        if not rows:
            return None
        r = rows[0]
        return StoredDetail(
            arxiv_id=r["paper_id"], detail=r["detail"], removed_claims=r["removed_claims"],
            verification_status=r["verification_status"], text_source=r["text_source"],
            based_on_abstract=r["based_on_abstract"], text_truncated=r["text_truncated"],
            text_mode=r["text_mode"], model=r["model"], prompt_version=r["prompt_version"],
        )

    # --- écriture ---

    def log_usage(self, row: dict) -> None:
        self.local.log_usage(row)
        try:
            self.http.post("/api_usage", headers={"Prefer": "return=minimal"}, json=row).raise_for_status()
        except httpx.HTTPError as e:  # ne jamais perdre une génération payée pour une ligne de journal
            log.error("api_usage: écriture en base impossible (%s) ; ligne gardée en local", e)

    def save_night(
        self, cfg: Config, edition: Edition, ranked: list[Ranked], articles: dict[str, Article]
    ) -> None:
        self.local.save_night(cfg, edition, ranked, articles)
        day = edition.date
        _, rank_version = load_prompt("rank")

        # Ordre imposé par les clés étrangères : articles, classement, édition, cartes.
        self._upsert("papers", [_paper_row(r.candidate.paper) for r in ranked], "arxiv_id")
        self._upsert(
            "papers",
            [
                {**_paper_row(a.paper), "full_text": a.text, "text_source": a.source,
                 "text_mode": a.mode, "text_truncated": a.truncated}
                for a in articles.values()
            ],
            "arxiv_id",
        )
        self._upsert(
            "rankings",
            [
                {
                    "paper_id": r.candidate.paper.arxiv_id, "date": day, "slot": r.candidate.slot,
                    "prefilter_score": r.candidate.prefilter_score, "relevance": r.rank.relevance,
                    "importance": r.rank.importance, "novelty": r.rank.novelty, "difficulty": r.rank.difficulty,
                    "why": r.rank.why, "final_score": r.final_score, "model": cfg.models.rank,
                    "prompt_version": rank_version,
                }
                for r in ranked
            ],
            "paper_id,date",
        )
        # L'édition n'est marquée prête qu'à la fin, une fois ses cartes en base.
        self._upsert(
            "editions",
            [{"date": day, "status": "pending", "cost_usd": edition.cost_usd, "notes": edition.notes}],
            "date",
        )
        self.http.delete("/edition_items", params={"edition_date": f"eq.{day}"}).raise_for_status()
        self._upsert(
            "edition_items",
            [{"edition_date": day, "paper_id": i.paper.arxiv_id, "position": i.position, "slot": i.slot} for i in edition.items],
            "edition_date,paper_id",
        )
        self._upsert(
            "cards",
            [{"paper_id": i.paper.arxiv_id, "card": i.card.model_dump(), "model": i.model, "prompt_version": i.prompt_version} for i in edition.items],
            "paper_id",
        )
        self._upsert("server_config", [{"id": 1, "config": server_config(cfg)}], "id")
        ready = {"status": edition.status}
        if edition.status == "ready":
            ready["ready_at"] = datetime.now(timezone.utc).isoformat()
        self.http.patch("/editions", params={"date": f"eq.{day}"}, json=ready).raise_for_status()
        log.info("base: édition %s écrite (%d cartes, %d articles classés)", day, len(edition.items), len(ranked))

    def save_detail(self, detail: StoredDetail) -> None:
        self.local.save_detail(detail)
        row = detail.model_dump()
        row["paper_id"] = row.pop("arxiv_id")
        self._upsert("details", [row], "paper_id")


def make_store(out: Path) -> LocalStore | SupabaseStore:
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_KEY")
    if url and key:
        log.info("stockage: Supabase")
        return SupabaseStore(url, key, out)
    log.info("stockage: fichiers locaux (%s)", out)
    return LocalStore(out)
