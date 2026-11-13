"""Teste l'Edge Function open-paper avec la session du propriétaire, comme le fera l'app.

    .venv/Scripts/python scripts/test_open_paper.py [arxiv_id]

Demande l'e-mail et le mot de passe du compte Supabase (saisis au clavier, jamais stockés),
ouvre une session avec la clé publique, puis appelle la fonction. Sans identifiant d'article,
prend le premier article de l'édition du jour qui n'a pas encore de détail (appel payant,
moins d'un centime) ; avec un article déjà ouvert, la réponse vient de la base, sans appel au modèle.
"""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    load_dotenv(ROOT / ".env")
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        print("SUPABASE_URL et SUPABASE_PUBLISHABLE_KEY doivent être dans .env")
        return 2

    email = input("E-mail du compte Supabase de l'app : ").strip()
    password = getpass.getpass("Mot de passe (non affiché) : ")
    with httpx.Client(base_url=url, headers={"apikey": key}, timeout=180) as http:
        r = http.post("/auth/v1/token", params={"grant_type": "password"}, json={"email": email, "password": password})
        if r.status_code != 200:
            print(f"Connexion refusée ({r.status_code}) : {r.json().get('msg') or r.json().get('error_description') or r.text[:200]}")
            return 1
        session = {"Authorization": f"Bearer {r.json()['access_token']}"}
        print("Connexion : ok")

        # Lecture comme l'app : clé publique + session, donc soumise aux règles RLS.
        r = http.get("/rest/v1/edition_today", params={"select": "position,arxiv_id,has_detail,card->>plain_title"}, headers=session)
        if r.status_code != 200:
            print(f"Lecture de edition_today refusée ({r.status_code}) : {r.text[:300]}")
            return 1
        cards = r.json()
        print(f"Lecture de l'édition avec votre session : {len(cards)} cartes")
        for c in cards:
            print(f"  {c['position']}. {c['arxiv_id']}  {'[détail en base] ' if c['has_detail'] else ''}{c['plain_title'][:70]}")

        arxiv_id = sys.argv[1] if len(sys.argv) > 1 else next((c["arxiv_id"] for c in cards if not c["has_detail"]), None)
        if arxiv_id is None:
            print("Tous les articles de l'édition ont déjà leur détail : passer un identifiant en argument.")
            return 0

        print(f"\nAppel de open-paper pour {arxiv_id} (jusqu'à une minute)...")
        r = http.post("/functions/v1/open-paper", json={"arxiv_id": arxiv_id}, headers=session)
        if r.status_code != 200:
            print(f"Échec ({r.status_code}) : {r.text[:500]}")
            if r.status_code == 401:
                print("-> 401 : désactiver « Verify JWT with legacy secret » dans les réglages de la fonction (docs/SUPABASE.md).")
            return 1
        body = r.json()
        d = body["detail"]
        print(f"Réussi ({'déjà en base, aucun appel au modèle' if body['cached'] else 'généré à l instant'})")
        print(f"  statut : {d['verification_status']}, modèle : {d['model']}, texte : {d['text_source']}")
        print(f"  affirmations sourcées : {len(d['detail']['claims'])}, retirées : {len(d['removed_claims'])}")
        print(f"  début de l'explication : {d['detail']['explanation_lay'][:200]}...")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
