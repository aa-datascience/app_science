"""Ligne de commande.

    python -m arxiv_digest run --no-llm     # ingestion + présélection seulement, gratuit
    python -m arxiv_digest run              # édition du jour, appels synchrones
    python -m arxiv_digest run --batch      # édition du jour via l'API Batches (-50 %, plus lent)
    python -m arxiv_digest compare          # essai comparatif des modèles (voir compare.py)
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
from .budget import affordable_size, estimate_cost_per_article, month_spent
from .config import REPO_ROOT, Config, load_config
from .fulltext import fetch_fulltext
from .llm import LLM, BatchFailed, LLMInvalid, LLMRefused, read_usage
from .models import Candidate, Edition, EditionItem, Ranked
from .prefilter import select_candidates
from .scoring import score_all, select_edition
from .steps import Article, Outcome, generate_verified, generate_verified_batch, make_article, rank

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


def ingest(cfg: Config, *, day: str, seen_ids: set[str], fixtures: Path | None) -> tuple[int, list[Candidate]]:
    """Étapes 1 et 2 : nouvelles soumissions du jour, puis présélection sans IA."""
    cats = list(cfg.categories.followed) + cfg.categories.exploration
    papers = new_submissions(
        fetch_feeds(cats, user_agent=cfg.arxiv.user_agent, delay_seconds=cfg.arxiv.delay_seconds, fixtures_dir=fixtures)
    )
    log.info("ingestion: %d nouvelles soumissions sur %d catégories", len(papers), len(cats))
    candidates = select_candidates(papers, cfg, seen_ids=seen_ids, seed=day)
    n_explo = sum(c.slot == "exploration" for c in candidates)
    log.info("présélection: %d candidats (%d exploration)", len(candidates), n_explo)
    return len(papers), candidates


def fetch_article(r: Ranked, cfg: Config, mode: str | None = None) -> Article:
    paper = r.candidate.paper
    text, source, truncated = fetch_fulltext(
        paper,
        user_agent=cfg.arxiv.user_agent,
        delay_seconds=cfg.arxiv.delay_seconds,
        max_chars=cfg.arxiv.max_fulltext_chars,
    )
    art = make_article(paper, text, source, truncated, mode or cfg.fulltext.mode)
    log.info("article %s: texte via %s, mode %s (%d caractères)", paper.arxiv_id, source, art.mode, len(art.text))
    return art


def _item(position: int, r: Ranked, art: Article, o: Outcome, cfg: Config) -> EditionItem:
    return EditionItem(
        position=position,
        slot=r.candidate.slot,
        paper=art.paper,
        rank=r.rank,
        final_score=r.final_score,
        content=o.content,
        verification_status=o.status,
        text_source=art.source,
        based_on_abstract=art.source == "abstract",
        text_truncated=art.truncated,
        text_mode=art.mode,
        corrected=o.corrected,
        model=cfg.models.generate,
        prompt_version=o.prompt_version,
    )


def run(
    cfg: Config, *, day: str, out: Path, no_llm: bool, size: int | None, fixtures: Path | None, batch: bool
) -> int:
    notes: list[str] = []
    seen_path, reserve_path, usage_path = out / "seen.json", out / "reserve.json", out / "api_usage.jsonl"
    seen_ids = set(_read_json(seen_path, []))

    n_papers, candidates = ingest(cfg, day=day, seen_ids=seen_ids, fixtures=fixtures)
    _write_json(out / "candidates" / f"{day}.json", [c.model_dump() for c in candidates])

    if no_llm:
        print(f"\n{n_papers} nouvelles soumissions, {len(candidates)} candidats. Les 10 premiers :")
        for c in candidates[:10]:
            print(f"  {c.prefilter_score:5.2f}  {c.paper.arxiv_id}  [{c.paper.primary_category}]  {c.paper.title[:80]}")
        print(f"\nCandidats écrits dans {out / 'candidates' / (day + '.json')}")
        return 0

    # Plafond mensuel : la taille de l'édition est fixée ici, avant tout appel payant,
    # pour ne jamais couper une édition en cours de route.
    usage = read_usage(usage_path)
    spent = month_spent(usage, day)
    per_article = estimate_cost_per_article(cfg, usage, batch=batch)
    wanted = size or cfg.edition.size
    target_size = affordable_size(
        wanted, monthly_cap=cfg.budget.monthly_usd, spent=spent, day=day, per_article=per_article
    )
    log.info(
        "budget: %.2f$ dépensés ce mois sur %.2f$, %.3f$ estimés par article -> %d articles sur %d",
        spent, cfg.budget.monthly_usd, per_article, target_size, wanted,
    )
    if target_size < wanted:
        msg = (
            f"Plafond mensuel ({cfg.budget.monthly_usd}$, {spent:.2f}$ dépensés) : "
            f"édition réduite de {wanted} à {target_size} articles."
        )
        notes.append(msg)
        log.warning(msg)

    llm = LLM(cfg, usage_path, day)
    items: list[EditionItem] = []
    ranked: list[Ranked] = []
    try:
        if target_size == 0:
            raise BatchFailed("Budget du jour insuffisant pour un seul article : pas d'édition.")

        # Étape 3 — classement (ou réserve de la semaine s'il n'y a rien de neuf)
        if candidates:
            ranked = score_all(rank(llm, candidates, cfg), cfg)
        else:
            ranked = [r for r in load_reserve(reserve_path, day) if r.candidate.paper.arxiv_id not in seen_ids]
            notes.append("Pas de nouvelles annonces arXiv : édition tirée de la réserve de la semaine.")
            log.info("aucun candidat: %d articles en réserve", len(ranked))

        selected = select_edition(ranked, cfg, target_size)

        # Étapes 4 à 6 — texte complet, génération, vérification
        if batch:
            arts = {r.candidate.paper.arxiv_id: fetch_article(r, cfg) for r in selected}
            outcomes = generate_verified_batch(llm, list(arts.values()), cfg)
            for r in selected:
                aid = r.candidate.paper.arxiv_id
                if aid in outcomes:
                    items.append(_item(len(items) + 1, r, arts[aid], outcomes[aid], cfg))
            if len(items) < len(selected):
                notes.append(f"{len(selected) - len(items)} articles abandonnés (génération en erreur).")
        else:
            chosen = {r.candidate.paper.arxiv_id for r in selected}
            # Remplaçants si un article échoue : le reste du classement principal.
            backups = sorted(
                (r for r in ranked if r.candidate.paper.arxiv_id not in chosen and r.candidate.slot == "main"),
                key=lambda r: -r.final_score,
            )
            for r in selected + backups:
                if len(items) >= len(selected):
                    break
                art = fetch_article(r, cfg)
                try:
                    outcome = generate_verified(llm, art, cfg)
                except (LLMRefused, LLMInvalid) as e:
                    log.warning("article %s abandonné: %r", art.paper.arxiv_id, e)
                    continue
                except anthropic.BadRequestError as e:
                    log.warning("article %s abandonné (requête refusée par l'API): %s", art.paper.arxiv_id, e.message)
                    continue
                items.append(_item(len(items) + 1, r, art, outcome, cfg))
    except BatchFailed as e:
        notes.append(str(e))
        log.error("%s", e)
    except anthropic.AuthenticationError:
        log.error("clé API Anthropic absente ou invalide (voir .env.example)")
        return 2
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        notes.append(f"Erreur de l'API Claude : {e}")
        log.error("erreur de l'API Claude: %s", e)

    # Étape 7 — publication (locale : un fichier JSON)
    edition = Edition(
        date=day, status="ready" if items else "failed", items=items, cost_usd=round(llm.run_spent, 4), notes=notes
    )
    path = out / "editions" / f"{day}.json"
    _write_json(path, edition.model_dump())

    used = {i.paper.arxiv_id for i in items}
    _write_json(seen_path, sorted(seen_ids | used))
    save_reserve(reserve_path, day, [r for r in ranked if r.candidate.paper.arxiv_id not in used], used)

    verified = sum(i.verification_status == "verified" for i in items)
    print(
        f"\nÉdition {day}: {edition.status}, {len(items)} articles ({verified} vérifiés), "
        f"{llm.run_spent:.3f}$ pour cette édition, {spent + llm.run_spent:.2f}$ ce mois"
    )
    for n in notes:
        print(f"  ! {n}")
    print(f"  -> {path}")
    return 0 if items else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arxiv_digest")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--date", help="AAAA-MM-JJ (défaut : aujourd'hui, Europe/Zurich)")
    common.add_argument("--config", type=Path, help="chemin de config.yaml")
    common.add_argument("--out", type=Path, default=REPO_ROOT / "out", help="dossier de sortie")
    common.add_argument("--fixtures", type=Path, help="lit les flux arXiv depuis ce dossier au lieu du réseau")

    p = sub.add_parser("run", parents=[common], help="construit l'édition du jour")
    p.add_argument("--no-llm", action="store_true", help="ingestion et présélection seulement (aucun appel payant)")
    p.add_argument("--size", type=int, help="nombre d'articles (défaut : config.yaml)")
    p.add_argument("--batch", action="store_true", help="génération et vérification via l'API Batches (-50 %%)")

    c = sub.add_parser("compare", parents=[common], help="essai comparatif des modèles sur quelques articles")
    c.add_argument("--n", type=int, default=4, help="nombre d'articles (dont un exploration)")
    c.add_argument("--max-usd", type=float, default=5.0, help="plafond de dépense de l'essai")
    c.add_argument("--configs", default="haiku,sonnet,opus", help="configurations à comparer")
    c.add_argument("--sections-for", default="haiku,sonnet", help="configurations à mesurer aussi en mode sections")
    c.add_argument("--batch-check", action="store_true", help="valide aussi le mode Batches sur un article (Haiku)")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # console Windows
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    load_dotenv(REPO_ROOT / ".env")

    needs_key = args.command == "compare" or not args.no_llm
    if needs_key and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.error("ANTHROPIC_API_KEY manquante : copier .env.example vers .env, ou lancer avec --no-llm")
        return 2

    day = args.date or datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat()
    cfg = load_config(args.config)
    if args.command == "compare":
        from .compare import compare

        return compare(
            cfg,
            day=day,
            out=args.out,
            fixtures=args.fixtures,
            n=args.n,
            max_usd=args.max_usd,
            labels=[s for s in args.configs.split(",") if s],
            sections_for=[s for s in args.sections_for.split(",") if s],
            batch_check=args.batch_check,
        )
    return run(cfg, day=day, out=args.out, no_llm=args.no_llm, size=args.size, fixtures=args.fixtures, batch=args.batch)


if __name__ == "__main__":
    raise SystemExit(main())
