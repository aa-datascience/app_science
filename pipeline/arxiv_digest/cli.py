"""Ligne de commande.

    python -m arxiv_digest run --no-llm     # ingestion + présélection seulement, gratuit
    python -m arxiv_digest run              # édition du jour (classement + cartes), appels synchrones
    python -m arxiv_digest run --batch      # idem, cartes via l'API Batches (-50 %) : pipeline de nuit
    python -m arxiv_digest open 2611.01234  # simule l'ouverture d'un article : génère son détail
    python -m arxiv_digest compare          # essai de coût et de qualité (voir compare.py)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic
import httpx
from dotenv import load_dotenv

from .arxiv import fetch_feeds, new_submissions
from .budget import affordable_size, can_open, estimate_cost, month_spent
from .config import REPO_ROOT, Config, load_config
from .fulltext import fetch_fulltext
from .llm import LLM, BatchFailed, LLMInvalid, LLMRefused
from .models import Candidate, Edition, EditionItem, Paper, Ranked
from .prefilter import select_candidates
from .scoring import score_all, select_edition
from .steps import Article, generate_detail, make_article, make_cards, rank
from .store import _write_json, make_store

log = logging.getLogger("arxiv_digest")


def ingest(
    cfg: Config, *, day: str, seen_ids: set[str], fixtures: Path | None
) -> tuple[int, list[Candidate], str]:
    """Nouvelles soumissions du jour, puis présélection sans IA.

    Renvoie (nombre de soumissions, candidats, date d'annonce la plus récente du flux).
    """
    cats = list(cfg.categories.followed) + cfg.categories.exploration
    papers = new_submissions(
        fetch_feeds(cats, user_agent=cfg.arxiv.user_agent, delay_seconds=cfg.arxiv.delay_seconds, fixtures_dir=fixtures)
    )
    log.info("ingestion: %d nouvelles soumissions sur %d catégories", len(papers), len(cats))
    candidates = select_candidates(papers, cfg, seen_ids=seen_ids, seed=day)
    n_explo = sum(c.slot == "exploration" for c in candidates)
    log.info("présélection: %d candidats (%d exploration)", len(candidates), n_explo)
    latest = max((p.published[:10] for p in papers), default="")
    return len(papers), candidates, latest


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
    cfg: Config, *, day: str, out: Path, no_llm: bool, size: int | None, fixtures: Path | None, batch: bool,
    stale: str = "reserve", force: bool = False,
) -> int:
    notes: list[str] = []
    store = make_store(out)
    # Le pipeline de nuit est lancé plusieurs fois par sécurité : une édition prête n'est pas refaite.
    if not no_llm and not force and store.has_edition(day):
        print(f"Édition {day} déjà prête : rien à faire (--force pour la refaire).")
        return 0
    seen_ids = store.seen_ids()

    n_papers, candidates, latest = ingest(cfg, day=day, seen_ids=seen_ids, fixtures=fixtures)
    # arXiv met ses flux à jour à minuit (heure de la côte Est). Avant cela, ou le week-end, le flux
    # contient encore l'annonce précédente : il ne faut pas en refaire une édition.
    if not no_llm and n_papers and latest < day:
        if stale == "wait":
            print(f"Flux arXiv pas encore à jour (dernière annonce : {latest}) : on attend le prochain lancement.")
            return 0
        log.info("flux arXiv non mis à jour aujourd'hui (dernière annonce: %s): édition tirée de la réserve", latest)
        candidates = []
    _write_json(out / "candidates" / f"{day}.json", [c.model_dump() for c in candidates])

    if no_llm:
        print(f"\n{n_papers} nouvelles soumissions, {len(candidates)} candidats. Les 10 premiers :")
        for c in candidates[:10]:
            print(f"  {c.prefilter_score:5.2f}  {c.paper.arxiv_id}  [{c.paper.primary_category}]  {c.paper.title[:80]}")
        print(f"\nCandidats écrits dans {out / 'candidates' / (day + '.json')}")
        return 0

    # Plafond mensuel : la taille de l'édition est fixée ici, avant tout appel payant,
    # pour ne jamais couper une édition en cours de route.
    usage = store.usage_rows(day)
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

    llm = LLM(cfg, store.log_usage, day)
    items: list[EditionItem] = []
    ranked: list[Ranked] = []
    articles: dict[str, Article] = {}
    try:
        if target_size == 0:
            raise BatchFailed("Budget du jour insuffisant pour une seule carte : pas d'édition.")

        # Classement (ou réserve de la semaine s'il n'y a rien de neuf)
        if candidates:
            ranked = score_all(rank(llm, candidates, cfg), cfg)
        else:
            ranked = [r for r in store.reserve(day) if r.candidate.paper.arxiv_id not in seen_ids]
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

        # Texte complet des articles de l'édition, stocké pour l'ouverture (gratuit : aucun modèle).
        if store.wants_fulltext:
            articles = {i.paper.arxiv_id: fetch_article(i.paper, cfg) for i in items}
    except BatchFailed as e:
        notes.append(str(e))
        log.error("%s", e)
    except anthropic.AuthenticationError:
        log.error("clé API Anthropic absente ou invalide (voir .env.example)")
        return 2
    except (anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        notes.append(f"Erreur de l'API Claude : {e}")
        log.error("erreur de l'API Claude: %s", e)

    # Publication : copie locale, et base Supabase si elle est configurée
    edition = Edition(
        date=day, status="ready" if items else "failed", items=items, cost_usd=round(llm.run_spent, 4), notes=notes
    )
    path = out / "editions" / f"{day}.json"
    try:
        store.save_night(cfg, edition, ranked, articles)
    except httpx.HTTPError as e:
        body = e.response.text[:300] if isinstance(e, httpx.HTTPStatusError) else ""
        log.error("écriture en base impossible: %s %s (copie locale : %s)", e, body, path)
        return 4


    print(
        f"\nÉdition {day}: {edition.status}, {len(items)} cartes, "
        f"{llm.run_spent:.4f}$ pour cette édition, {spent + llm.run_spent:.2f}$ ce mois"
    )
    for n in notes:
        print(f"  ! {n}")
    print(f"  -> {path}")
    return 0 if items else 1


# ---------- À l'ouverture d'un article : détail, généré une fois puis stocké ----------


def open_paper(cfg: Config, *, day: str, out: Path, arxiv_id: str) -> int:
    """Ce que fait l'Edge Function open-paper quand une carte est ouverte dans l'app."""
    store = make_store(out)
    stored = store.get_detail(arxiv_id)
    if stored is not None:
        print(f"Détail déjà généré ({stored.verification_status}, {stored.model}) : aucun appel.")
        return 0
    paper = store.find_paper(arxiv_id)
    if paper is None:
        log.error("article %s absent des éditions (lancer d'abord `run`)", arxiv_id)
        return 1

    usage = store.usage_rows(day)
    spent, estimate = month_spent(usage, day), estimate_cost(cfg, usage, "detail")
    if not can_open(monthly_cap=cfg.budget.monthly_usd, spent=spent, estimate=estimate):
        log.warning(
            "plafond mensuel: %.2f$ dépensés sur %.2f$, %.3f$ estimés pour ce détail -> refusé",
            spent, cfg.budget.monthly_usd, estimate,
        )
        return 3

    llm = LLM(cfg, store.log_usage, day)
    try:
        detail = generate_detail(llm, store.article(paper) or fetch_article(paper, cfg), cfg)
    except anthropic.AuthenticationError:
        log.error("clé API Anthropic absente ou invalide (voir .env.example)")
        return 2
    except (LLMRefused, LLMInvalid, anthropic.APIConnectionError, anthropic.APIStatusError) as e:
        log.error("détail %s: échec (%r)", arxiv_id, e)
        return 1
    store.save_detail(detail)
    print(
        f"Détail {arxiv_id}: {detail.verification_status}, {len(detail.detail.claims)} affirmations sourcées, "
        f"{len(detail.removed_claims)} retirées, {llm.run_spent:.4f}$"
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
    p.add_argument("--stale", choices=["wait", "reserve"], default="reserve",
                   help="si le flux arXiv n'est pas à jour : attendre (ne rien faire) ou puiser dans la réserve")
    p.add_argument("--force", action="store_true", help="refait l'édition même si elle est déjà prête")

    nt = sub.add_parser("notify", parents=[common], help="envoie la notification du matin ou du soir si elle est due")
    nt.add_argument("kind", choices=["morning", "evening"])
    nt.add_argument("--dry-run", action="store_true", help="décide et affiche, sans envoyer ni marquer")

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

    if args.command == "notify":
        from .notify import notify

        return notify(out=args.out, kind=args.kind, dry_run=args.dry_run)

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
    return run(
        cfg, day=day, out=args.out, no_llm=args.no_llm, size=args.size, fixtures=args.fixtures, batch=args.batch,
        stale=args.stale, force=args.force,
    )


if __name__ == "__main__":
    raise SystemExit(main())
