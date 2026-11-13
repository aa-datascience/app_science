"""Ligne de commande.

    python -m arxiv_digest run --no-llm     # ingestion + présélection seulement, gratuit
    python -m arxiv_digest run              # édition du jour (classement + cartes), appels synchrones
    python -m arxiv_digest run --batch      # idem, cartes via l'API Batches (-50 %) : pipeline de nuit
    python -m arxiv_digest open 2611.01234  # simule l'ouverture d'un article : génère son détail
    python -m arxiv_digest compare          # essai de coût et de qualité (voir compare.py)
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
from .budget import affordable_size, can_open, estimate_cost, month_spent
from .config import REPO_ROOT, Config, load_config
from .fulltext import fetch_fulltext
from .llm import LLM, BatchFailed, LLMInvalid, LLMRefused, read_usage
from .models import Candidate, Edition, EditionItem, Paper, Ranked, StoredDetail
from .prefilter import select_candidates
from .scoring import score_all, select_edition
from .steps import Article, generate_detail, make_article, make_cards, rank

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
    """Nouvelles soumissions du jour, puis présélection sans IA."""
    cats = list(cfg.categories.followed) + cfg.categories.exploration
    papers = new_submissions(
        fetch_feeds(cats, user_agent=cfg.arxiv.user_agent, delay_seconds=cfg.arxiv.delay_seconds, fixtures_dir=fixtures)
    )
    log.info("ingestion: %d nouvelles soumissions sur %d catégories", len(papers), len(cats))
    candidates = select_candidates(papers, cfg, seen_ids=seen_ids, seed=day)
    n_explo = sum(c.slot == "exploration" for c in candidates)
    log.info("présélection: %d candidats (%d exploration)", len(candidates), n_explo)
    return len(papers), candidates


def fetch_article(paper: Paper, cfg: Config, mode: str | None = None) -> Article:
    text, source, truncated = fetch_fulltext(
        paper,
        user_agent=cfg.arxiv.user_agent,
        delay_seconds=cfg.arxiv.delay_seconds,
        max_chars=cfg.arxiv.max_fulltext_chars,
    )
    art = make_article(paper, text, source, truncated, mode or cfg.fulltext.mode)
    log.info("article %s: texte via %s, mode %s (%d caractères)", paper.arxiv_id, source, art.mode, len(art.text))
    return art


# ---------- La nuit : édition = classement + cartes ----------


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
    per_card = estimate_cost(cfg, usage, "card", batch=batch)
    wanted = size or cfg.edition.size
    target_size = affordable_size(wanted, monthly_cap=cfg.budget.monthly_usd, spent=spent, day=day, per_article=per_card)
    log.info(
        "budget: %.2f$ dépensés ce mois sur %.2f$, %.4f$ estimés par carte -> %d cartes sur %d",
        spent, cfg.budget.monthly_usd, per_card, target_size, wanted,
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
            raise BatchFailed("Budget du jour insuffisant pour une seule carte : pas d'édition.")

        # Classement (ou réserve de la semaine s'il n'y a rien de neuf)
        if candidates:
            ranked = score_all(rank(llm, candidates, cfg), cfg)
        else:
            ranked = [r for r in load_reserve(reserve_path, day) if r.candidate.paper.arxiv_id not in seen_ids]
            notes.append("Pas de nouvelles annonces arXiv : édition tirée de la réserve de la semaine.")
            log.info("aucun candidat: %d articles en réserve", len(ranked))

        selected = select_edition(ranked, cfg, target_size)

        # Cartes : titre et résumé seulement, un appel par article
        cards, version = make_cards(llm, [r.candidate.paper for r in selected], cfg, batch=batch)
        for r in selected:
            card = cards.get(r.candidate.paper.arxiv_id)
            if card is not None:
                items.append(
                    EditionItem(
                        position=len(items) + 1,
                        slot=r.candidate.slot,
                        paper=r.candidate.paper,
                        rank=r.rank,
                        final_score=r.final_score,
                        card=card,
                        model=cfg.models.card,
                        prompt_version=version,
                    )
                )
        if len(items) < len(selected):
            notes.append(f"{len(selected) - len(items)} cartes en erreur, articles retirés de l'édition.")
    except BatchFailed as e:
        notes.append(str(e))
        log.error("%s", e)
    except anthropic.AuthenticationError:
        log.error("clé API Anthropic absente ou invalide (voir .env.example)")
        return 2
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        notes.append(f"Erreur de l'API Claude : {e}")
        log.error("erreur de l'API Claude: %s", e)

    # Publication (locale : un fichier JSON)
    edition = Edition(
        date=day, status="ready" if items else "failed", items=items, cost_usd=round(llm.run_spent, 4), notes=notes
    )
    path = out / "editions" / f"{day}.json"
    _write_json(path, edition.model_dump())

    used = {i.paper.arxiv_id for i in items}
    _write_json(seen_path, sorted(seen_ids | used))
    save_reserve(reserve_path, day, [r for r in ranked if r.candidate.paper.arxiv_id not in used], used)

    print(
        f"\nÉdition {day}: {edition.status}, {len(items)} cartes, "
        f"{llm.run_spent:.4f}$ pour cette édition, {spent + llm.run_spent:.2f}$ ce mois"
    )
    for n in notes:
        print(f"  ! {n}")
    print(f"  -> {path}")
    return 0 if items else 1


# ---------- À l'ouverture d'un article : détail, généré une fois puis stocké ----------


def find_paper(out: Path, arxiv_id: str) -> Paper | None:
    """Cherche l'article dans les éditions locales, de la plus récente à la plus ancienne."""
    for path in sorted((out / "editions").glob("*.json"), reverse=True):
        for item in _read_json(path, {}).get("items", []):
            if item["paper"]["arxiv_id"] == arxiv_id:
                return Paper.model_validate(item["paper"])
    return None


def open_paper(cfg: Config, *, day: str, out: Path, arxiv_id: str) -> int:
    """Ce que fera l'Edge Function quand une carte est ouverte dans l'app."""
    stored = out / "details" / f"{arxiv_id}.json"
    if stored.exists():
        d = StoredDetail.model_validate(_read_json(stored, {}))
        print(f"Détail déjà généré ({d.verification_status}, {d.model}) : aucun appel. -> {stored}")
        return 0
    paper = find_paper(out, arxiv_id)
    if paper is None:
        log.error("article %s absent des éditions locales (lancer d'abord `run`)", arxiv_id)
        return 1

    usage_path = out / "api_usage.jsonl"
    usage = read_usage(usage_path)
    spent, estimate = month_spent(usage, day), estimate_cost(cfg, usage, "detail")
    if not can_open(monthly_cap=cfg.budget.monthly_usd, spent=spent, estimate=estimate):
        log.warning(
            "plafond mensuel: %.2f$ dépensés sur %.2f$, %.3f$ estimés pour ce détail -> refusé",
            spent, cfg.budget.monthly_usd, estimate,
        )
        return 3

    llm = LLM(cfg, usage_path, day)
    try:
        detail = generate_detail(llm, fetch_article(paper, cfg), cfg)
    except anthropic.AuthenticationError:
        log.error("clé API Anthropic absente ou invalide (voir .env.example)")
        return 2
    except (LLMRefused, LLMInvalid, anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        log.error("détail %s: échec (%r)", arxiv_id, e)
        return 1
    _write_json(stored, detail.model_dump())
    print(
        f"Détail {arxiv_id}: {detail.verification_status}, {len(detail.detail.claims)} affirmations sourcées, "
        f"{len(detail.removed_claims)} retirées, {llm.run_spent:.4f}$ -> {stored}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arxiv_digest")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--date", help="AAAA-MM-JJ (défaut : aujourd'hui, Europe/Zurich)")
    common.add_argument("--config", type=Path, help="chemin de config.yaml")
    common.add_argument("--out", type=Path, default=REPO_ROOT / "out", help="dossier de sortie")
    common.add_argument("--fixtures", type=Path, help="lit les flux arXiv depuis ce dossier au lieu du réseau")

    p = sub.add_parser("run", parents=[common], help="construit l'édition du jour (classement + cartes)")
    p.add_argument("--no-llm", action="store_true", help="ingestion et présélection seulement (aucun appel payant)")
    p.add_argument("--size", type=int, help="nombre d'articles (défaut : config.yaml)")
    p.add_argument("--batch", action="store_true", help="cartes via l'API Batches (-50 %%)")

    o = sub.add_parser("open", parents=[common], help="simule l'ouverture d'un article : génère et stocke son détail")
    o.add_argument("arxiv_id")

    c = sub.add_parser("compare", parents=[common], help="essai de coût et de qualité sur quelques articles")
    c.add_argument("--n", type=int, default=4, help="nombre d'articles (dont un exploration)")
    c.add_argument("--max-usd", type=float, default=2.0, help="plafond de dépense de l'essai")
    c.add_argument("--detail-models", default="sonnet,haiku", help="modèles à comparer pour le détail")
    c.add_argument("--no-batch", action="store_true", help="cartes en synchrone plutôt que par l'API Batches")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # console Windows
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    load_dotenv(REPO_ROOT / ".env")

    needs_key = args.command != "run" or not args.no_llm
    if needs_key and not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        log.error("ANTHROPIC_API_KEY manquante : copier .env.example vers .env, ou lancer avec --no-llm")
        return 2

    day = args.date or datetime.now(ZoneInfo("Europe/Zurich")).date().isoformat()
    cfg = load_config(args.config)
    if args.command == "open":
        return open_paper(cfg, day=day, out=args.out, arxiv_id=args.arxiv_id)
    if args.command == "compare":
        from .compare import compare

        return compare(
            cfg,
            day=day,
            out=args.out,
            fixtures=args.fixtures,
            n=args.n,
            max_usd=args.max_usd,
            detail_labels=[s for s in args.detail_models.split(",") if s],
            batch=not args.no_batch,
        )
    return run(cfg, day=day, out=args.out, no_llm=args.no_llm, size=args.size, fixtures=args.fixtures, batch=args.batch)


if __name__ == "__main__":
    raise SystemExit(main())
