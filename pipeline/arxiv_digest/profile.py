"""Profil appris (V2, étape 3) : poids et niveaux mis à jour par le feedback, sans modèle.

Les poids vivent en base (`profile_weights`) ; `config.yaml` ne sert qu'à les initialiser.
Avant chaque édition, `sync_profile` :

1. initialise la base à partir de `config.yaml` si elle est vide ;
2. apprend des feedbacks explicites arrivés depuis la dernière fois ;
3. apprend des signaux implicites (lu, ignoré) des éditions terminées : celles qu'une édition plus
   récente a remplacées (la dernière édition parue peut encore être en cours de lecture) ;
4. rapproche chaque poids de sa valeur de repos, une fois par édition traitée ;
5. applique poids, niveaux et réglages de l'app à la configuration de la nuit.

Règles décidées le 14 novembre 2026 (docs/V2_PLAN.md, section 6) :
- « interesting » +0,05 ; « not for me » −0,05 ; Save +0,10 ;
- « lu » (vue profondeur ouverte) +0,025 ; « ignoré » −0,0125, seulement si la carte est restée
  au moins 2 secondes à l'écran ; un article qui a reçu un avis explicite ne compte pas en implicite ;
- la catégorie principale reçoit le changement entier, une catégorie secondaire la moitié ;
- seuls les mots-clés déjà présents bougent ; les mots-clés négatifs ne sont pas appris ;
- trois « too easy » (ou « too hard ») de plus que l'inverse font monter (descendre) le niveau ;
- retour de 2 % vers la valeur de repos par édition ; bornes 0,2 à 2,0 ; un poids verrouillé ne bouge pas.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

from .config import Config

log = logging.getLogger(__name__)

STEP = {"interesting": 0.05, "not_interesting": -0.05, "saved": 0.10, "read": 0.025, "ignored": -0.0125}
EXPLICIT = {"interesting", "not_interesting", "saved"}
DECAY = 0.02
MIN_W, MAX_W = 0.2, 2.0
SECONDARY = 0.5  # part du changement reçue par une catégorie secondaire (cross-list)
MIN_VIEW_MS = 2000  # en dessous, une carte passée n'est pas un « ignoré »
LEVELS = ["beginner", "intermediate", "expert"]
LEVEL_THRESHOLD = 3
SIZE_RANGE = (3, 12)  # nombre d'articles par édition accepté depuis l'app
LABELS = {
    "interesting": "interesting", "not_interesting": "not for me", "saved": "saved",
    "read": "read", "ignored": "skipped",
}


def _clamp(w: float) -> float:
    return round(max(MIN_W, min(MAX_W, w)), 4)


def initial_rows(cfg: Config) -> tuple[list[dict], list[dict]]:
    """Poids et niveaux de départ, tirés de config.yaml. Un mot-clé négatif porte un poids négatif."""
    weights = [
        {"kind": "category", "key": k, "weight": w, "baseline": w, "locked": False}
        for k, w in cfg.categories.followed.items()
    ]
    weights += [
        {"kind": "keyword", "key": k, "weight": w, "baseline": w, "locked": False}
        for k, w in cfg.prefilter.keywords_positive.items()
    ]
    weights += [
        {"kind": "keyword", "key": k, "weight": -w, "baseline": -w, "locked": False}
        for k, w in cfg.prefilter.keywords_negative.items()
    ]
    levels = [{"category": c, "level": lv, "drift": 0, "locked": False} for c, lv in cfg.profile.levels.items()]
    return weights, levels


def implicit_signals(items: list[dict], events: list[dict], explicit_ids: set[str]) -> list[dict]:
    """Signaux « lu » et « ignoré » des éditions terminées.

    items  : articles des éditions, avec `paper_id`, `edition_date` et l'article sous `papers`.
    events : événements de lecture de ces éditions (`opened`, `viewed` avec `duration_ms`).
    """
    opened: set[tuple[str, str]] = set()
    viewed: dict[tuple[str, str], int] = defaultdict(int)
    for e in events:
        key = (e["edition_date"], e["paper_id"])
        if e["event"] == "opened":
            opened.add(key)
        elif e["event"] == "viewed":
            viewed[key] += e.get("duration_ms") or 0
    out = []
    for i in items:
        if i["paper_id"] in explicit_ids:
            continue
        key = (i["edition_date"], i["paper_id"])
        if key in opened:
            out.append({"type": "read", "paper": i["papers"]})
        elif viewed[key] >= MIN_VIEW_MS:
            out.append({"type": "ignored", "paper": i["papers"]})
    return out


def _reason(counts: Counter, day: str) -> str:
    parts = [f"{n} {LABELS[t]}" for t, n in sorted(counts.items(), key=lambda x: list(STEP).index(x[0]))]
    return ", ".join(parts)


def learn(
    weights: list[dict], levels: list[dict], signals: list[dict], *, editions: int, day: str
) -> tuple[list[dict], list[dict], list[dict]]:
    """Applique les signaux puis le retour vers la valeur de repos.

    signals : {"type": ..., "paper": {"title", "abstract", "categories"}}.
    Renvoie (poids modifiés, niveaux modifiés, lignes du journal).
    """
    by_key = {(w["kind"], w["key"]): dict(w) for w in weights}
    delta: dict[tuple[str, str], float] = defaultdict(float)
    why: dict[tuple[str, str], Counter] = defaultdict(Counter)
    lv = {r["category"]: dict(r) for r in levels}
    lv_why: dict[str, Counter] = defaultdict(Counter)

    for s in signals:
        paper, kind = s["paper"], s["type"]
        cats = paper.get("categories") or []
        if kind in ("too_easy", "too_hard"):
            if cats:
                row = lv.setdefault(cats[0], {"category": cats[0], "level": "intermediate", "drift": 0, "locked": False})
                if not row["locked"]:
                    row["drift"] += 1 if kind == "too_easy" else -1
                    lv_why[cats[0]][kind] += 1
            continue
        step = STEP[kind]
        for n, cat in enumerate(cats):
            if ("category", cat) in by_key:
                delta[("category", cat)] += step * (1.0 if n == 0 else SECONDARY)
                why[("category", cat)][kind] += 1
        text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
        for (k, key), w in by_key.items():
            if k == "keyword" and w["weight"] > 0 and key.lower() in text:
                delta[(k, key)] += step
                why[(k, key)][kind] += 1

    changed_w, changes = [], []
    for key, w in by_key.items():
        if w["locked"] or w["weight"] <= 0:  # verrouillé, ou mot-clé négatif : jamais appris
            continue
        new = w["weight"] + delta.get(key, 0.0)
        for _ in range(editions):
            new += (w["baseline"] - new) * DECAY
        new = _clamp(new)
        if abs(new - w["weight"]) < 1e-9:
            continue
        if key in why:  # le seul retour vers la valeur de repos n'est pas journalisé
            changes.append({
                "source": "feedback", "kind": w["kind"], "key": w["key"],
                "old_value": f"{w['weight']:.3f}", "new_value": f"{new:.3f}", "reason": _reason(why[key], day),
            })
        changed_w.append({**w, "weight": new})

    changed_l = []
    for cat, counts in lv_why.items():
        row = lv[cat]
        old = row["level"]
        i = LEVELS.index(old)
        if row["drift"] >= LEVEL_THRESHOLD and i < len(LEVELS) - 1:
            row["level"], row["drift"] = LEVELS[i + 1], 0
        elif row["drift"] <= -LEVEL_THRESHOLD and i > 0:
            row["level"], row["drift"] = LEVELS[i - 1], 0
        row["drift"] = max(-LEVEL_THRESHOLD, min(LEVEL_THRESHOLD, row["drift"]))
        changed_l.append(row)
        if row["level"] != old:
            easy, hard = counts["too_easy"], counts["too_hard"]
            changes.append({
                "source": "feedback", "kind": "level", "key": cat, "old_value": old, "new_value": row["level"],
                "reason": f"{easy} too easy, {hard} too hard",
            })
    return changed_w, changed_l, changes


def apply_profile(cfg: Config, weights: list[dict], levels: list[dict], settings: dict) -> Config:
    """Configuration de la nuit : celle de config.yaml, avec les poids, niveaux et réglages de la base."""
    out = cfg.model_copy(deep=True)
    if weights:
        cats = {w["key"]: w["weight"] for w in weights if w["kind"] == "category"}
        kws = [w for w in weights if w["kind"] == "keyword"]
        out.categories.followed = cats
        out.categories.exploration = [c for c in cfg.categories.exploration if c not in cats]
        out.prefilter.keywords_positive = {w["key"]: w["weight"] for w in kws if w["weight"] > 0}
        out.prefilter.keywords_negative = {w["key"]: -w["weight"] for w in kws if w["weight"] < 0}
    out.profile.levels = {**cfg.profile.levels, **{r["category"]: r["level"] for r in levels}}
    size = settings.get("edition_size")
    if isinstance(size, int) and not isinstance(size, bool):
        out.edition.size = max(SIZE_RANGE[0], min(SIZE_RANGE[1], size))
    return out


def sync_profile(store, cfg: Config, day: str, *, learning: bool = True) -> Config:
    """Apprend (si `learning`) puis renvoie la configuration à utiliser. Sans base, renvoie `cfg` tel quel."""
    if not hasattr(store, "profile_state"):
        return cfg
    state = store.profile_state()
    weights, levels, prof = state["weights"], state["levels"], state["profile"]
    if not learning:
        return apply_profile(cfg, weights, levels, prof.get("settings") or {})

    if not weights:
        weights, levels = initial_rows(cfg)
        store.save_profile(weights, levels, [], {})
        log.info("profil: initialisé depuis config.yaml (%d poids)", len(weights))

    cursor = prof.get("learned_feedback_id") or 0
    feedback = store.feedback_since(cursor)
    signals = [{"type": f["type"], "paper": f["papers"]} for f in feedback]

    # Une édition est terminée quand une plus récente existe : avant cela, elle peut encore être lue.
    after = prof.get("learned_through") or "1970-01-01"
    latest = store.latest_edition()
    done: list[str] = []
    if latest and after < latest:
        reading = store.reading_between(after, latest)
        done = reading["editions"]
        signals += implicit_signals(reading["items"], reading["events"], reading["explicit_ids"])
    through = max(done, default=after)
    editions = len(done)

    changed_w, changed_l, changes = learn(weights, levels, signals, editions=editions, day=day)
    new_cursor: dict = {"learned_feedback_id": max([cursor, *(f["id"] for f in feedback)])}
    if done:
        new_cursor["learned_through"] = through
    store.save_profile(changed_w, changed_l, changes, new_cursor)
    log.info(
        "profil: %d signaux, %d éditions terminées, %d poids et %d niveaux modifiés",
        len(signals), editions, len(changed_w), len(changed_l),
    )
    merged_w = {(w["kind"], w["key"]): w for w in [*weights, *changed_w]}
    merged_l = {r["category"]: r for r in [*levels, *changed_l]}
    return apply_profile(cfg, list(merged_w.values()), list(merged_l.values()), prof.get("settings") or {})
