"""Ligne de commande : une journée d'arXiv -> out/editions/DATE.json.

    python -m arxiv_digest run              # pipeline complet (appelle l'API Claude)
    python -m arxiv_digest run --no-llm     # ingestion + présélection seulement, gratuit
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
from dotenv import load_dotenv

from .arxiv import fetch_feeds, new_submissions
from .config import REPO_ROOT, Config, load_config
from .fulltext import fetch_fulltext
from .llm import LLM, BudgetExceeded, LLMInvalid, LLMRefused
from .models import Edition, EditionItem, Ranked
from .prefilter import select_candidates
from .scoring import score_all, select_edition
from .steps import generate_verified, rank

log = logging.getLogger("arxiv_digest")
RESERVE_DAYS = 7


def _read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_reserve(path: Path, day: str) -> list[Ranked]:
    """Bons articles des 7 derniers jours non retenus (pour les jours sans annonces arXiv)."""
    cutoff = (date.fromisoformat(day) - timedelta(days=RESERVE_DAYS)).isoformat()
    return [Ranked.model_validate(r["ranked"]) for r in _read_json(path, []) if r["date"] >= cutoff]


def save_reserve(path: Path, day: str, unselected: list[Ranked], used_ids: set[str]) -> None:
    cutoff = (date.fromisoformat(day) - timedelta(days=RESERVE_DAYS)).isoformat()
    rows = [
        r
        for r in _read_json(path, [])
        if r["date"] >= cutoff and r["ranked"]["candidate"]["paper"]["arxiv_id"] not in used_ids
    ]
    known = {r["ranked"]["candidate"]["paper"]["arxiv_id"] for r in rows}
    rows += [
        {"date": day, "ranked": r.model_dump()}
        for r in unselected
        if r.candidate.paper.arxiv_id not in known
    ]
    _write_json(path, rows)


def run(cfg: Config, *, day: str, out: Path, no_llm: bool, size: int | None, fixtures: Path | None) -> int:
    notes: list[str] = []
    seen_path, reserve_path = out / "seen.json", out / "reserve.json"
    seen_ids = set(_read_json(seen_path, []))

    # Étape 1 — ingestion
    cats = list(cfg.categories.followed) + cfg.categories.exploration
    papers = new_submissions(
        fetch_feeds(cats, user_agent=cfg.arxiv.user_agent, delay_seconds=cfg.arxiv.delay_seconds, fixtures_dir=fixtures)
    )
    log.info("ingestion: %d nouvelles soumissions sur %d catégories", len(papers), len(cats))

    # Étape 2 — présélection
    candidates = select_candidates(papers, cfg, seen_ids=seen_ids, seed=day)
    n_explo = sum(c.slot == "exploration" for c in candidates)
    log.info("présélection: %d candidats (%d exploration)", len(candidates), n_explo)
    _write_json(out / "candidates" / f"{day}.json", [c.model_dump() for c in candidates])

    if no_llm:
        print(f"\n{len(papers)} nouvelles soumissions, {len(candidates)} candidats. Les 10 premiers :")
        for c in candidates[:10]:
            print(f"  {c.prefilter_score:5.2f}  {c.paper.arxiv_id}  [{c.paper.primary_category}]  {c.paper.title[:80]}")
        print(f"\nCandidats écrits dans {out / 'candidates' / (day + '.json')}")
        return 0

    llm = LLM(cfg, out / "api_usage.jsonl", day)
    items: list[EditionItem] = []
    ranked: list[Ranked] = []
    try:
        # Étape 3 — classement (ou réserve de la semaine s'il n'y a rien de neuf)
        if candidates:
            ranked = score_all(rank(llm, candidates, cfg), cfg)
        else:
            ranked = [r for r in load_reserve(reserve_path, day) if r.candidate.paper.arxiv_id not in seen_ids]
            notes.append("Pas de nouvelles annonces arXiv : édition tirée de la réserve de la semaine.")
            log.info("aucun candidat: %d articles en réserve", len(ranked))

        selected = select_edition(ranked, cfg, size)
        target = len(selected)
        chosen = {r.candidate.paper.arxiv_id for r in selected}
        # Remplaçants si un article échoue : le reste du classement principal.
        backups = sorted(
            (r for r in ranked if r.candidate.paper.arxiv_id not in chosen and r.candidate.slot == "main"),
            key=lambda r: -r.final_score,
        )

        # Étapes 4 à 6 — texte complet, génération, vérification
        for r in selected + backups:
            if len(items) >= target:
                break
            paper = r.candidate.paper
            text, source, truncated = fetch_fulltext(
                paper,
                user_agent=cfg.arxiv.user_agent,
                delay_seconds=cfg.arxiv.delay_seconds,
                max_chars=cfg.arxiv.max_fulltext_chars,
            )
            log.info("article %s: texte via %s (%d caractères)", paper.arxiv_id, source, len(text))
            try:
                content, status, version = generate_verified(llm, paper, text, source, truncated, cfg)
            except (LLMRefused, LLMInvalid) as e:
                log.warning("article %s abandonné: %r", paper.arxiv_id, e)
                continue
            except anthropic.BadRequestError as e:
                log.warning("article %s abandonné (requête refusée par l'API): %s", paper.arxiv_id, e.message)
                continue
            items.append(
                EditionItem(
                    position=len(items) + 1,
                    slot=r.candidate.slot,
                    paper=paper,
                    rank=r.rank,
                    final_score=r.final_score,
                    content=content,
                    verification_status=status,
                    text_source=source,
                    based_on_abstract=source == "abstract",
                    text_truncated=truncated,
                    model=cfg.models.generate,
                    prompt_version=version,
                )
            )
    except BudgetExceeded as e:
        notes.append(f"Plafond de dépense atteint : {e}")
        log.warning("plafond de dépense atteint: %s", e)
    except anthropic.AuthenticationError:
        log.error("clé API Anthropic absente ou invalide (voir .env.example)")
        return 2
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        notes.append(f"Erreur de l'API Claude : {e}")
        log.error("erreur de l'API Claude: %s", e)

    # Étape 7 — publication (locale : un fichier JSON)
    edition = Edition(
        date=day, status="ready" if items else "failed", items=items, cost_usd=round(llm.spent, 4), notes=notes
    )
    path = out / "editions" / f"{day}.json"
    _write_json(path, edition.model_dump())

    used = {i.paper.arxiv_id for i in items}
    _write_json(seen_path, sorted(seen_ids | used))
    save_reserve(reserve_path, day, [r for r in ranked if r.candidate.paper.arxiv_id not in used], used)

    verified = sum(i.verification_status == "verified" for i in items)
    print(f"\nÉdition {day}: {edition.status}, {len(items)} articles ({verified} vérifiés), {llm.spent:.3f}$ dépensés aujourd'hui")
    for n in notes:
        print(f"  ! {n}")
    print(f"  -> {path}")
    return 0 if items else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arxiv_digest")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run", help="construit l'édition du jour")
    p.add_argument("--date", help="AAAA-MM-JJ (défaut : aujourd'hui, Europe/Zurich)")
    p.add_argument("--no-llm", action="store_true", help="ingestion et présélection seulement (aucun appel payant)")
    p.add_argument("--size", type=int, help="nombre d'articles (défaut : config.yaml)")
    p.add_argument("--config", type=Path, help="chemin de config.yaml")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "out", help="dossier de sortie")
    p.add_argument("--fixtures", type=Path, help="lit les flux arXiv depuis ce dossier au lieu du réseau")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # console Windows
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    load_dotenv(REPO_ROOT / ".env")

    if not args.no_llm and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.error("ANTHROPIC_API_KEY manquante : copier .env.example vers .env, ou lancer avec --no-llm")
        return 2

    day = args.date or datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat()
    return run(load_config(args.config), day=day, out=args.out, no_llm=args.no_llm, size=args.size, fixtures=args.fixtures)


if __name__ == "__main__":
    raise SystemExit(main())
