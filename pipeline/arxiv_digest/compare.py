"""Essai comparatif : les mêmes articles générés et vérifiés par plusieurs configurations de modèles.

Écrit comparison/AAAA-MM-JJ.md (lisible) et .json (brut). Le classement reste sur le
modèle rapide dans tous les cas. Appels synchrones, pour avoir le résultat tout de suite ;
le coût en mode Batches est calculé à partir des tokens mesurés.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from .cli import fetch_article, ingest
from .config import REPO_ROOT, Config
from .llm import LLM, BatchFailed, BudgetExceeded, LLMInvalid, LLMRefused, usage_cost
from .scoring import score_all, select_edition
from .steps import Article, Outcome, generate_verified, generate_verified_batch, make_article, rank

log = logging.getLogger(__name__)

PRESETS = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
    "opus": "claude-opus-5-5",
}
ARTICLES_PER_MONTH = 8 * 30


def _n(x: int) -> str:
    return f"{x:,}".replace(",", " ")


def _with_models(cfg: Config, model: str) -> Config:
    c = cfg.model_copy(deep=True)
    c.models.generate = c.models.verify = model
    return c


def _stats(cfg: Config, rows: list[dict]) -> dict:
    """Tokens et coût d'un ensemble de lignes du journal, plus le coût recalculé en Batches sans cache."""
    s = {"calls": len(rows), "input": 0, "cache_write": 0, "cache_read": 0, "output": 0, "usd": 0.0, "usd_batch": 0.0}
    for r in rows:
        s["input"] += r["input_tokens"]
        s["cache_write"] += r["cache_write_5m_tokens"] + r["cache_write_1h_tokens"]
        s["cache_read"] += r["cache_read_tokens"]
        s["output"] += r["output_tokens"]
        s["usd"] += r["cost_usd"]
        all_in = r["input_tokens"] + r["cache_write_5m_tokens"] + r["cache_write_1h_tokens"] + r["cache_read_tokens"]
        flat = {"input_tokens": all_in, "cache_write_5m_tokens": 0, "cache_write_1h_tokens": 0,
                "cache_read_tokens": 0, "output_tokens": r["output_tokens"], "batch": True}
        s["usd_batch"] += usage_cost(cfg.budget.prices[r["model"]], flat)
    return s


def _verdict(o: Outcome) -> str:
    first = o.checks[0] if o.checks else None
    if first is None:
        return "non vérifié (vérification en erreur)"
    bad = sum(not v.supported for v in first.verdicts)
    detail = f"{len(first.verdicts)} affirmations contrôlées, {bad} non appuyées, {len(first.unsupported_numbers)} chiffres absents de l'article"
    if not o.corrected:
        return f"vérifié du premier coup ({detail})"
    end = "vérifié après correction" if o.status == "verified" else "NON VÉRIFIÉ après correction"
    return f"{end} (1er passage : {detail})"


def render_markdown(day: str, cfg: Config, arts: list[dict], runs: list[dict], rank_stats: dict, notes: list[str], cap: float, total: float) -> str:
    L: list[str] = [f"# Essai comparatif des modèles — {day}", ""]
    L += [f"{len(arts)} articles, appels synchrones, cache de 5 min sur le texte de l'article, effort `{cfg.models.effort}`. "
          f"Dépense totale de l'essai : **{total:.2f} $** (plafond {cap:.0f} $).", ""]
    for n in notes:
        L += [f"> {n}", ""]

    L += ["## Coûts mesurés", "",
          "| Configuration | Texte | Articles | Tokens entrée (dont lus en cache) | Tokens sortie | Coût mesuré | Par article | Mois, synchrone | Mois, Batches |",
          "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for run in runs:
        s, n = run["stats"], run["n_done"]
        if not n:
            L.append(f"| {run['label']} | {run['mode']} | 0 | – | – | – | – | – | – |")
            continue
        tok_in = s["input"] + s["cache_write"] + s["cache_read"]
        month = s["usd"] / n * ARTICLES_PER_MONTH + rank_stats["usd"] * 30
        month_b = s["usd_batch"] / n * ARTICLES_PER_MONTH + rank_stats["usd"] * 30
        L.append(
            f"| {run['label']} (`{run['model']}`) | {run['mode']} | {n} | {_n(tok_in)} ({_n(s['cache_read'])}) | {_n(s['output'])} | "
            f"{s['usd']:.3f} $ | {s['usd'] / n:.3f} $ | {month:.1f} $ | {month_b:.1f} $ |"
        )
    L += ["",
          f"- **Mois** = 8 articles par jour pendant 30 jours, plus le classement quotidien ({rank_stats['usd']:.4f} $ mesuré aujourd'hui sur `{cfg.models.rank}`, "
          f"{_n(rank_stats['input'])} tokens en entrée, {_n(rank_stats['output'])} en sortie).",
          "- **Synchrone** : extrapolation directe du coût mesuré (cache de 5 min compris).",
          "- **Batches** : calculé, pas mesuré — mêmes tokens, sans cache, à -50 %.",
          "- Les tokens de sortie comprennent la réflexion du modèle.",
          "- Petit échantillon : la longueur des articles varie beaucoup, l'extrapolation est un ordre de grandeur.", ""]

    L += ["## Vérification", "", "| Article | " + " | ".join(f"{r['label']} / {r['mode']}" for r in runs) + " |",
          "| --- |" + " --- |" * len(runs)]
    for a in arts:
        cells = []
        for run in runs:
            o = run["outcomes"].get(a["id"])
            cells.append("–" if o is None else ("✔" if o["status"] == "verified" and not o["corrected"] else "✔ après correction" if o["status"] == "verified" else "✘ non vérifié"))
        L.append(f"| {a['id']} | " + " | ".join(cells) + " |")
    L.append("")

    for i, a in enumerate(arts, 1):
        L += [f"## {i}. {a['title']}", "",
              f"[arXiv:{a['id']}](https://arxiv.org/abs/{a['id']}) · {a['categories']} · emplacement **{a['slot']}** · "
              f"texte : {a['source']}, {_n(a['chars_full'])} caractères"
              + (f" (mode sections : {_n(a['chars_sections'])}, soit {100 * a['chars_sections'] // max(1, a['chars_full'])} %)" if a["chars_sections"] else " (mode sections : non applicable, texte complet gardé)"),
              "", f"*Pourquoi cet article :* {a['why']}", ""]
        for run in runs:
            o = run["outcomes"].get(a["id"])
            L += [f"### {run['label']} — texte {run['mode']}", ""]
            if o is None:
                L += ["Pas de résultat (non lancé ou en erreur).", ""]
                continue
            c = o["content"]
            L += [f"**Vérification :** {o['verdict']}", ""]
            if o["feedback"]:
                L += [f"*Corrections demandées au 1er passage :* {o['feedback']}", ""]
            L += [f"**Carte** — {c['card']['plain_title']}", "",
                  f"- Ce qu'ils ont trouvé : {c['card']['finding']}",
                  f"- Pourquoi c'est important : {c['card']['why_it_matters']}",
                  f"- Tags : {', '.join(c['card']['tags'])} · difficulté {c['card']['difficulty']}/5 · {c['card']['reading_minutes']} min", "",
                  "**Explication (curieux)**", "", c["explanation_lay"], "",
                  "**Explication (physicien)**", "", c["explanation_expert"], "",
                  "**Contexte**", "",
                  f"- Avant : {c['context']['before']}",
                  f"- Ce que l'article change : {c['context']['change']}",
                  f"- Limites : {c['context']['limitations']}", ""]
    return "\n".join(L)


def compare(
    cfg: Config, *, day: str, out: Path, fixtures: Path | None, n: int, max_usd: float,
    labels: list[str], sections_for: list[str], batch_check: bool,
) -> int:
    unknown = [x for x in labels + sections_for if x not in PRESETS]
    if unknown:
        log.error("configurations inconnues: %s (choix: %s)", unknown, ", ".join(PRESETS))
        return 2
    llm = LLM(cfg, out / "api_usage.jsonl", day, hard_cap_usd=max_usd)
    notes: list[str] = []

    _, candidates = ingest(cfg, day=day, seen_ids=set(), fixtures=fixtures)
    if not candidates:
        log.error("aucun candidat aujourd'hui (pas d'annonces arXiv ?)")
        return 1
    try:
        ranked = score_all(rank(llm, candidates, cfg), cfg)
    except anthropic.AuthenticationError:
        log.error("clé API Anthropic absente ou invalide")
        return 2
    rank_stats = _stats(cfg, list(llm.records))
    selected = select_edition(ranked, cfg, n)

    # Texte complet récupéré une seule fois par article, puis décliné en mode sections.
    fulls: dict[str, Article] = {}
    sects: dict[str, Article] = {}
    arts_meta: list[dict] = []
    for r in selected:
        full = fetch_article(r, cfg, mode="full")
        sec = make_article(full.paper, full.text, full.source, full.truncated, "sections")
        aid = full.paper.arxiv_id
        fulls[aid] = full
        if sec.mode == "sections":
            sects[aid] = sec
        arts_meta.append({
            "id": aid, "title": full.paper.title, "categories": ", ".join(full.paper.categories),
            "slot": r.candidate.slot, "why": r.rank.why, "source": full.source,
            "chars_full": len(full.text), "chars_sections": len(sec.text) if sec.mode == "sections" else 0,
        })

    plan = [(label, "complet", fulls) for label in labels] + [(label, "sections", sects) for label in sections_for if sects]
    if sections_for and not sects:
        notes.append("Mode sections : aucun des articles n'a de sections reconnaissables, mesure impossible.")
    runs: list[dict] = []
    stopped = False
    for label, mode, pool in plan:
        c = _with_models(cfg, PRESETS[label])
        tag = f"{label}/{mode}"
        outcomes: dict[str, dict] = {}
        before = len(llm.records)
        for aid, art in pool.items():
            if stopped:
                break
            try:
                o = generate_verified(llm, art, c, label=tag)
            except BudgetExceeded as e:
                notes.append(f"Essai interrompu au plafond : {e}. Les configurations suivantes sont incomplètes.")
                stopped = True
                break
            except (LLMRefused, LLMInvalid, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                log.warning("%s %s: %r", tag, aid, e)
                notes.append(f"{tag}, article {aid} : échec ({type(e).__name__}).")
                continue
            outcomes[aid] = {
                "status": o.status, "corrected": o.corrected, "verdict": _verdict(o),
                "feedback": o.checks[0].feedback if o.corrected and o.checks else "",
                "content": o.content.model_dump(),
                "checks": [ch.model_dump() for ch in o.checks],
            }
        # Coût : seulement les articles aboutis, pour un coût par article juste.
        rows = [r for r in llm.records[before:] if r.get("arxiv_id") in outcomes]
        runs.append({"label": label, "mode": mode, "model": PRESETS[label], "outcomes": outcomes,
                     "n_done": len(outcomes), "stats": _stats(cfg, rows)})
        log.info("%s: %d articles, %.3f$ (essai: %.3f$)", tag, len(outcomes), runs[-1]["stats"]["usd"], llm.run_spent)

    if batch_check and not stopped:
        # Validation réelle du chemin Batches, sur un article et le modèle le moins cher.
        c = _with_models(cfg, PRESETS["haiku"])
        first = next(iter(fulls.values()))
        try:
            res = generate_verified_batch(llm, [first], c)
            ok = first.paper.arxiv_id in res
            notes.append(f"Mode Batches validé en réel sur {first.paper.arxiv_id} (Haiku) : {'résultat obtenu' if ok else 'aucun résultat'}.")
        except (BatchFailed, BudgetExceeded, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            notes.append(f"Mode Batches : échec de la validation réelle ({e}).")

    cdir = REPO_ROOT / "comparison"
    cdir.mkdir(exist_ok=True)
    md = render_markdown(day, cfg, arts_meta, runs, rank_stats, notes, max_usd, llm.run_spent)
    (cdir / f"{day}.md").write_text(md, encoding="utf-8")
    (cdir / f"{day}.json").write_text(
        json.dumps({"date": day, "articles": arts_meta, "runs": runs, "ranking": rank_stats, "notes": notes,
                    "total_usd": round(llm.run_spent, 4)}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nEssai terminé : {llm.run_spent:.2f}$ dépensés. -> {cdir / (day + '.md')}")
    for nt in notes:
        print(f"  ! {nt}")
    return 0
