"""Essai de coût et de qualité de l'architecture en deux temps, sur quelques articles du jour.

- Nuit : classement puis cartes (titre + résumé) avec le modèle `card`, via l'API Batches.
- Ouverture : détail (texte complet) avec chacun des modèles demandés, citations vérifiées sans modèle.

Écrit comparison/AAAA-MM-JJ.md (lisible) et .json (brut).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from .cli import fetch_article, ingest
from .config import REPO_ROOT, Config
from .llm import LLM, BatchFailed, BudgetExceeded, LLMInvalid, LLMRefused
from .scoring import score_all, select_edition
from .steps import generate_detail, make_cards, rank

log = logging.getLogger(__name__)

PRESETS = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}
CARDS_PER_DAY, OPENS_PER_DAY, DAYS = 8, 3, 30


def _n(x: int) -> str:
    return f"{x:,}".replace(",", " ")


def _stats(rows: list[dict]) -> dict:
    return {
        "calls": len(rows),
        "input": sum(r["input_tokens"] + r["cache_write_5m_tokens"] + r["cache_write_1h_tokens"] + r["cache_read_tokens"] for r in rows),
        "output": sum(r["output_tokens"] for r in rows),
        "usd": sum(r["cost_usd"] for r in rows),
    }


def render_markdown(day: str, cfg: Config, data: dict) -> str:
    arts, rank_s, card_s, runs, notes = data["articles"], data["ranking"], data["cards"], data["runs"], data["notes"]
    n_cards = card_s["n_done"]
    per_card = card_s["stats"]["usd"] / n_cards if n_cards else 0.0
    night = rank_s["usd"] + CARDS_PER_DAY * per_card

    L = [f"# Essai de l'architecture en deux temps — {day}", "",
         f"{len(arts)} articles du jour. Dépense totale de l'essai : **{data['total_usd']:.3f} $** (plafond {data['cap_usd']:.0f} $).", ""]
    for nt in notes:
        L += [f"> {nt}", ""]

    L += ["## Coût de la nuit", "",
          "| Étape | Modèle | Appels | Tokens entrée | Tokens sortie | Coût mesuré | Unité |",
          "| --- | --- | ---: | ---: | ---: | ---: | --- |",
          f"| Classement | `{cfg.models.rank}` | {rank_s['calls']} | {_n(rank_s['input'])} | {_n(rank_s['output'])} | {rank_s['usd']:.4f} $ | par nuit ({data['n_candidates']} candidats) |",
          f"| Cartes | `{cfg.models.card}`{', Batches' if card_s['batch'] else ''} | {card_s['stats']['calls']} | {_n(card_s['stats']['input'])} | {_n(card_s['stats']['output'])} | {card_s['stats']['usd']:.4f} $ | {per_card:.5f} $ par carte |",
          "", f"Une nuit complète (classement + {CARDS_PER_DAY} cartes) : **{night:.4f} $**.", ""]

    L += ["## Coût par article ouvert", "",
          "| Modèle du détail | Articles | Tokens entrée | Tokens sortie | Coût mesuré | Par article ouvert | Affirmations | Retirées | Non vérifiés |",
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for run in runs:
        s, n = run["stats"], run["n_done"]
        o = run["outcomes"].values()
        claims = sum(len(x["detail"]["claims"]) + len(x["removed_claims"]) for x in o)
        removed = sum(len(x["removed_claims"]) for x in o)
        unverified = sum(x["verification_status"] == "unverified" for x in o)
        per = f"{s['usd'] / n:.4f} $" if n else "–"
        L.append(f"| {run['label']} (`{run['model']}`) | {n} | {_n(s['input'])} | {_n(s['output'])} | {s['usd']:.4f} $ | {per} | {claims} | {removed} | {unverified} sur {n} |")
    L += ["", "Les tokens de sortie comprennent la réflexion du modèle. Appels synchrones, sans cache (un seul appel par article).", ""]

    L += [f"## Extrapolation mensuelle ({CARDS_PER_DAY} cartes et {OPENS_PER_DAY} articles ouverts par jour, {DAYS} jours)", "",
          "| Modèle du détail | Nuits | Articles ouverts | Total par mois | Part du plafond de " + f"{cfg.budget.monthly_usd:.0f} $ |",
          "| --- | ---: | ---: | ---: | ---: |"]
    for run in runs:
        if not run["n_done"]:
            continue
        opens = run["stats"]["usd"] / run["n_done"] * OPENS_PER_DAY * DAYS
        total = night * DAYS + opens
        L.append(f"| {run['label']} | {night * DAYS:.2f} $ | {opens:.2f} $ | **{total:.2f} $** | {100 * total / cfg.budget.monthly_usd:.0f} % |")
    L += ["", f"Petit échantillon ({len(arts)} articles) : la longueur des articles varie beaucoup, c'est un ordre de grandeur.", ""]

    for i, a in enumerate(arts, 1):
        L += [f"## {i}. {a['title']}", "",
              f"[arXiv:{a['id']}](https://arxiv.org/abs/{a['id']}) · {a['categories']} · emplacement **{a['slot']}** · "
              f"texte : {a['source']}, {_n(a['chars'])} caractères", "",
              f"*Pourquoi cet article :* {a['why']}", ""]
        card = card_s["cards"].get(a["id"])
        L += [f"### Carte (`{cfg.models.card}`, titre et résumé seulement)", ""]
        if card:
            L += [f"**{card['plain_title']}**", "",
                  f"- Ce qu'ils ont trouvé : {card['finding']}",
                  f"- Pourquoi c'est important : {card['why_it_matters']}",
                  f"- Tags : {', '.join(card['tags'])} · difficulté {card['difficulty']}/5", ""]
        else:
            L += ["Pas de carte (en erreur).", ""]
        for run in runs:
            o = run["outcomes"].get(a["id"])
            L += [f"### Détail — {run['label']} (`{run['model']}`)", ""]
            if o is None:
                L += ["Pas de résultat (non lancé ou en erreur).", ""]
                continue
            d, kept, removed = o["detail"], o["detail"]["claims"], o["removed_claims"]
            status = "vérifié" if o["verification_status"] == "verified" else "NON VÉRIFIÉ"
            L += [f"**Vérification des citations :** {status} — {len(kept)} citations retrouvées dans l'article, {len(removed)} introuvables (affirmations retirées).", "",
                  "**Explication (curieux)**", "", d["explanation_lay"], "",
                  "**Explication (physicien)**", "", d["explanation_expert"], "",
                  "**Contexte**", "",
                  f"- Avant : {d['context']['before']}",
                  f"- Ce que l'article change : {d['context']['change']}",
                  f"- Limites : {d['context']['limitations']}", "",
                  "**Affirmations sourcées**", ""]
            L += [f"- {c['statement']}\n  > {c['quote']}" for c in kept] or ["Aucune."]
            if removed:
                L += ["", "**Affirmations retirées (citation introuvable)**", ""]
                L += [f"- {c['statement']}\n  > {c['quote']}" for c in removed]
            L.append("")
    return "\n".join(L)


def compare(
    cfg: Config, *, day: str, out: Path, fixtures: Path | None, n: int, max_usd: float,
    detail_labels: list[str], batch: bool,
) -> int:
    unknown = [x for x in detail_labels if x not in PRESETS]
    if unknown:
        log.error("modèles inconnus: %s (choix: %s)", unknown, ", ".join(PRESETS))
        return 2
    llm = LLM(cfg, out / "api_usage.jsonl", day, hard_cap_usd=max_usd)
    notes: list[str] = []

    # --- Nuit : classement ---
    _, candidates, _ = ingest(cfg, day=day, seen_ids=set(), fixtures=fixtures)
    if not candidates:
        log.error("aucun candidat aujourd'hui (pas d'annonces arXiv ?)")
        return 1
    try:
        ranked = score_all(rank(llm, candidates, cfg), cfg)
    except anthropic.AuthenticationError:
        log.error("clé API Anthropic absente ou invalide")
        return 2
    rank_stats = _stats(list(llm.records))
    selected = select_edition(ranked, cfg, n)
    papers = [r.candidate.paper for r in selected]

    # --- Nuit : cartes ---
    before = len(llm.records)
    cards: dict = {}
    try:
        cards, _ = make_cards(llm, papers, cfg, batch=batch, label="night")
    except BatchFailed as e:
        notes.append(f"Cartes par lot : échec ({e}).")
    card_data = {
        "batch": batch, "n_done": len(cards), "stats": _stats(llm.records[before:]),
        "cards": {k: v.model_dump() for k, v in cards.items()},
    }
    log.info("cartes: %d sur %d, %.4f$", len(cards), len(papers), card_data["stats"]["usd"])

    # --- Ouverture : détail, texte complet récupéré une fois par article ---
    arts = {p.arxiv_id: fetch_article(p, cfg) for p in papers}
    arts_meta = [
        {"id": r.candidate.paper.arxiv_id, "title": r.candidate.paper.title,
         "categories": ", ".join(r.candidate.paper.categories), "slot": r.candidate.slot, "why": r.rank.why,
         "source": arts[r.candidate.paper.arxiv_id].source, "chars": len(arts[r.candidate.paper.arxiv_id].text)}
        for r in selected
    ]
    runs: list[dict] = []
    stopped = False
    for label in detail_labels:
        c = cfg.model_copy(deep=True)
        c.models.generate = PRESETS[label]
        outcomes: dict[str, dict] = {}
        before = len(llm.records)
        for aid, art in arts.items():
            if stopped:
                break
            try:
                outcomes[aid] = generate_detail(llm, art, c, label=label).model_dump()
            except BudgetExceeded as e:
                notes.append(f"Essai interrompu au plafond : {e}. Les mesures suivantes sont incomplètes.")
                stopped = True
            except (LLMRefused, LLMInvalid, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                log.warning("détail %s %s: %r", label, aid, e)
                notes.append(f"Détail {label}, article {aid} : échec ({type(e).__name__}).")
        # Coût : seulement les articles aboutis, pour un coût par article juste.
        rows = [r for r in llm.records[before:] if r.get("arxiv_id") in outcomes]
        runs.append({"label": label, "model": PRESETS[label], "outcomes": outcomes, "n_done": len(outcomes), "stats": _stats(rows)})
        log.info("détail %s: %d articles, %.4f$ (essai: %.4f$)", label, len(outcomes), runs[-1]["stats"]["usd"], llm.run_spent)

    data = {"date": day, "cap_usd": max_usd, "total_usd": round(llm.run_spent, 4), "n_candidates": len(candidates),
            "articles": arts_meta, "ranking": rank_stats, "cards": card_data, "runs": runs, "notes": notes}
    cdir = REPO_ROOT / "comparison"
    cdir.mkdir(exist_ok=True)
    (cdir / f"{day}.md").write_text(render_markdown(day, cfg, data), encoding="utf-8")
    (cdir / f"{day}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEssai terminé : {llm.run_spent:.3f}$ dépensés. -> {cdir / (day + '.md')}")
    for nt in notes:
        print(f"  ! {nt}")
    return 0
