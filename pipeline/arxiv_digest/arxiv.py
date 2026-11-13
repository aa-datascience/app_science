"""Étape 1 — Ingestion : flux Atom quotidiens d'arXiv, un par catégorie."""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

from .models import Paper

log = logging.getLogger(__name__)

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "dc": "http://purl.org/dc/elements/1.1/",
}
FEED_URL = "https://rss.arxiv.org/atom/{category}"
_ID_RE = re.compile(r"oai:arXiv\.org:(?P<id>.+?)(?:v(?P<v>\d+))?$")
_ABSTRACT_RE = re.compile(r"Abstract:\s*(.*)", re.S)


def parse_feed(xml_text: str) -> list[Paper]:
    """Parse un flux Atom rss.arxiv.org en liste de Paper (toutes annonces confondues)."""
    root = ET.fromstring(xml_text)
    papers: list[Paper] = []
    for entry in root.findall("a:entry", NS):
        m = _ID_RE.match((entry.findtext("a:id", "", NS)).strip())
        if not m:
            continue
        summary = entry.findtext("a:summary", "", NS)
        am = _ABSTRACT_RE.search(summary)
        abstract = " ".join((am.group(1) if am else summary).split())
        creators = entry.findtext("dc:creator", "", NS)
        papers.append(
            Paper(
                arxiv_id=m.group("id"),
                version=int(m.group("v") or 1),
                title=" ".join(entry.findtext("a:title", "", NS).split()),
                authors=[a.strip() for a in creators.split(",") if a.strip()],
                abstract=abstract,
                categories=[c.get("term", "") for c in entry.findall("a:category", NS)],
                announce_type=(entry.findtext("arxiv:announce_type", "new", NS)).strip(),
                published=entry.findtext("a:published", "", NS).strip(),
            )
        )
    return papers


def new_submissions(papers: list[Paper]) -> list[Paper]:
    """Garde les nouvelles soumissions et cross-lists ; exclut les simples nouvelles versions.

    Dédoublonne par identifiant (un article apparaît dans plusieurs flux).
    """
    seen: dict[str, Paper] = {}
    for p in papers:
        if p.announce_type not in ("new", "cross"):
            continue
        # Préférer l'entrée "new" (catégorie principale en tête) à l'entrée "cross".
        if p.arxiv_id not in seen or p.announce_type == "new":
            seen[p.arxiv_id] = p
    return list(seen.values())


def fetch_feeds(
    categories: list[str],
    *,
    user_agent: str,
    delay_seconds: float,
    fixtures_dir: Path | None = None,
) -> list[Paper]:
    """Télécharge les flux des catégories (ou les lit depuis fixtures_dir, pour les tests)."""
    papers: list[Paper] = []
    if fixtures_dir is not None:
        for cat in categories:
            f = fixtures_dir / f"atom_{cat}.xml"
            if f.exists():
                papers += parse_feed(f.read_text(encoding="utf-8"))
        return papers

    transport = httpx.HTTPTransport(retries=3)
    with httpx.Client(
        headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True, transport=transport
    ) as client:
        for i, cat in enumerate(categories):
            if i:
                time.sleep(delay_seconds)
            try:
                r = client.get(FEED_URL.format(category=cat))
                r.raise_for_status()
                found = parse_feed(r.text)
                log.info("ingestion %s: %d entrées", cat, len(found))
                papers += found
            except (httpx.HTTPError, ET.ParseError) as e:
                log.warning("ingestion %s: échec (%s)", cat, e)
    return papers
