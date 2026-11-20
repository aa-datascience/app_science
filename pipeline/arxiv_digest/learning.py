"""Concepts et questions du détail (V2, étape 4), contrôlés sans appel au modèle.

Portage TypeScript à l'identique : supabase/functions/open-paper/learning.ts, avec les cas
partagés de tests/fixtures/learning_cases.json. Toute modification se fait des deux côtés.

- Questions : la citation doit se trouver dans l'article (même correspondance tolérante que
  les affirmations) ; un QCM doit avoir de 2 à 6 options distinctes, dont la réponse. Une question
  qui échoue est retirée ; cela ne change pas le statut « vérifié » du détail.
- Concepts : identifiant normalisé ; un identifiant déjà en base est réutilisé tel quel (sa fiche
  n'est jamais réécrite) ; une nouvelle fiche doit avoir un nom et ses deux définitions.
  Les définitions sont des rappels de cours : elles ne sont pas vérifiées par une citation.
"""

from __future__ import annotations

import re
import unicodedata

from .citations import normalize, quote_found

MAX_CONCEPTS = 3
MAX_QUESTIONS = 3
MAX_RELATED = 3
MAX_KNOWN = 150  # concepts connus donnés au modèle (décision 5)
MIN_OPTIONS, MAX_OPTIONS = 2, 6
MAX_ID_CHARS = 60


def slugify(s: str) -> str:
    """« Andreev Bound State » ou « andreev_bound-state » -> « andreev-bound-state »."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:MAX_ID_CHARS].strip("-")


def _clean(s) -> str:
    return s.strip() if isinstance(s, str) else ""


def check_questions(questions: list[dict], text: str) -> tuple[list[dict], list[dict]]:
    """Renvoie (questions gardées, nettoyées ; questions retirées). Trois gardées au plus."""
    hay = normalize(text)
    kept: list[dict] = []
    removed: list[dict] = []
    for q in questions:
        kind = q.get("kind")
        prompt, answer = _clean(q.get("prompt")), _clean(q.get("answer"))
        ok = len(kept) < MAX_QUESTIONS and kind in ("mcq", "short") and bool(prompt) and bool(answer)
        ok = ok and quote_found(_clean(q.get("quote")), hay)
        options: list[str] = []
        if ok and kind == "mcq":
            seen: set[str] = set()
            for o in q.get("options") or []:
                o = _clean(o)
                if o and normalize(o) not in seen:
                    seen.add(normalize(o))
                    options.append(o)
            # La réponse doit être l'une des options ; on garde le texte exact de l'option.
            match = next((o for o in options if normalize(o) == normalize(answer)), None)
            ok = MIN_OPTIONS <= len(options) <= MAX_OPTIONS and match is not None
            answer = match or answer
        if ok:
            kept.append({
                "kind": kind, "prompt": prompt, "options": options, "answer": answer,
                "explanation": _clean(q.get("explanation")), "quote": _clean(q.get("quote")),
            })
        else:
            removed.append(q)
    return kept, removed


def resolve_concepts(entries: list[dict], known_ids: set[str] | list[str]) -> dict:
    """Décide, pour les concepts proposés, lesquels réutiliser et lesquels créer.

    Renvoie {"paper": [identifiants, dans l'ordre], "new": [fiches à créer], "links": [[a, b], …]}
    avec a < b. `known_ids` : tous les identifiants déjà en base.
    """
    known = set(known_ids)
    paper: list[str] = []
    new: list[dict] = []
    related: dict[str, list[str]] = {}
    for e in entries:
        if len(paper) >= MAX_CONCEPTS:
            break
        cid = slugify(_clean(e.get("id")) or _clean(e.get("name")))
        if not cid or cid in paper:
            continue
        if cid not in known:
            name, simple, expert = _clean(e.get("name")), _clean(e.get("simple_definition")), _clean(e.get("expert_definition"))
            if not (name and simple and expert):
                continue  # un identifiant inconnu sans fiche complète ne peut pas être créé
            new.append({"id": cid, "name": name, "simple_definition": simple, "expert_definition": expert})
        paper.append(cid)
        related[cid] = [slugify(_clean(r)) for r in (e.get("related") or [])][:MAX_RELATED]
    exists = known | set(paper)
    links: list[list[str]] = []
    for cid in paper:
        for r in related[cid]:
            pair = sorted((cid, r))
            if r and r != cid and r in exists and pair not in links:
                links.append(pair)
    return {"paper": paper, "new": new, "links": links}


def known_for_prompt(concepts: list[dict], category: str, limit: int = MAX_KNOWN) -> str:
    """Liste « - id: name » des concepts connus : ceux du même domaine d'abord, puis les plus récents."""
    ordered = sorted(concepts, key=lambda c: c.get("created_at") or "", reverse=True)
    ordered = sorted(ordered, key=lambda c: c.get("primary_category") != category)  # tri stable
    lines = [f"- {c['id']}: {c['name']}" for c in ordered[:limit]]
    return "\n".join(lines) or "(none yet)"
