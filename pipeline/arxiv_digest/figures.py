"""Figures d'un article : extraction (HTML arXiv, sinon source LaTeX), conversion en WebP, copie.

Seules les figures choisies par les prompts (une pour la carte, une à trois pour la vue profondeur)
sont copiées dans le stockage, redimensionnées et compressées. Les autres ne sont que décrites
(label, légende, adresse d'origine) pour que le modèle puisse choisir.
"""

from __future__ import annotations

import io
import logging
import re
import time
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .models import Figure

log = logging.getLogger(__name__)

MAX_WIDTH = 1400
WEBP_QUALITY = 80
MIN_DISPLAY_WIDTH, MIN_DISPLAY_HEIGHT = 120, 60  # en dessous : logo ou pictogramme
MIN_CAPTION_CHARS = 15
CAPTION_CHARS_IN_PROMPT = 700
EPRINT = "eprint:"  # préfixe d'une image qui vit dans l'archive LaTeX de l'article

_LABEL = re.compile(r"(?:Figure|Fig\.?)\s*([A-Za-z]?\d+[A-Za-z]?)", re.I)


# ---------- extraction depuis la version HTML d'arXiv (LaTeXML) ----------


def _caption_text(figcaption) -> str:
    """Légende sans son étiquette « Figure 1: », équations rendues en $LaTeX$."""
    for tag in figcaption.select(".ltx_tag"):
        tag.decompose()
    for math in figcaption.find_all("math"):
        tex = math.get("alttext") or math.get_text(" ", strip=True)
        math.replace_with(f"${tex}$")
    return re.sub(r"\s+", " ", figcaption.get_text(" ")).strip()


def extract_figures_html(html: str, page_url: str) -> list[Figure]:
    """Figures de premier niveau, avec toutes leurs images (sous-figures comprises) et leur légende."""
    soup = BeautifulSoup(html, "html.parser")
    figures: list[Figure] = []
    seen: set[str] = set()
    for fig in soup.select("figure.ltx_figure"):
        if fig.find_parent("figure") is not None:
            continue  # panneau d'une figure déjà traitée
        captions = [c for c in fig.find_all("figcaption")]
        main = next((c for c in captions if c.find_parent("figure") is fig and c.select_one(".ltx_tag")), None)
        if main is None:
            continue
        m = _LABEL.search(main.select_one(".ltx_tag").get_text(" "))
        if not m or m.group(1) in seen:
            continue
        label = m.group(1)

        images: list[str] = []
        small = 0
        for el in fig.select("img.ltx_graphics, object.ltx_graphics"):
            src = el.get("src") or el.get("data")
            if not src:
                continue
            w, h = el.get("width"), el.get("height")
            if w and h and w.isdigit() and h.isdigit() and (int(w) < MIN_DISPLAY_WIDTH or int(h) < MIN_DISPLAY_HEIGHT):
                small += 1
                continue
            images.append(urljoin(page_url, src))
        if not images:
            continue  # rien d'exploitable (ou seulement des pictogrammes)

        # Légendes des panneaux, s'il y en a, puis la légende principale.
        parts = [_caption_text(c) for c in captions if c is not main]
        caption = " ".join(p for p in [_caption_text(main), *parts] if p)
        if len(caption) < MIN_CAPTION_CHARS:
            continue  # figure décorative : pas de légende digne de ce nom
        seen.add(label)
        figures.append(Figure(label=label, caption=caption, images=images))
    return figures


# ---------- repli : figures de la source LaTeX ----------

_FIG_ENV = re.compile(r"\\begin\{figure\*?\}(.*?)\\end\{figure\*?\}", re.S)
_INCLUDE = re.compile(r"\\includegraphics\*?(?:\[[^\]]*\])?\{([^}]+)\}")
_USABLE = (".png", ".jpg", ".jpeg", ".pdf", ".svg")  # .eps : pas de conversion disponible


def _braced(text: str, start: int) -> str:
    """Contenu du groupe {…} qui s'ouvre à `start`, accolades imbriquées comprises."""
    depth, i = 0, start
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1 : i]
        i += 1
    return text[start + 1 :]


def _latex_caption(block: str) -> str:
    m = re.search(r"\\caption\*?(?:\[[^\]]*\])?\s*\{", block)
    if not m:
        return ""
    caption = _braced(block, m.end() - 1)
    caption = re.sub(r"\\label\{[^}]*\}", "", caption)
    return re.sub(r"\s+", " ", caption).strip()


def _resolve(name: str, members: list[str]) -> str | None:
    """Fichier de l'archive correspondant à un \\includegraphics (extension souvent omise)."""
    name = name.strip().lstrip("./")
    for cand in [name, *[name + ext for ext in _USABLE]]:
        hits = [m for m in members if m == cand or m.endswith("/" + cand)]
        if hits and hits[0].lower().endswith(_USABLE):
            return hits[0]
    return None


def extract_figures_latex(tex: str, members: list[str]) -> list[Figure]:
    """Figures de la source LaTeX, numérotées dans l'ordre. `tex` : source sans commentaires."""
    figures: list[Figure] = []
    for n, block in enumerate(_FIG_ENV.findall(tex), start=1):
        caption = _latex_caption(block)
        images = [EPRINT + f for f in (_resolve(name, members) for name in _INCLUDE.findall(block)) if f]
        if images and len(caption) >= MIN_CAPTION_CHARS:
            figures.append(Figure(label=str(n), caption=caption, images=images))
    return figures


# ---------- texte donné aux modèles ----------


def figures_for_prompt(figures: list[Figure]) -> str:
    """La liste des figures telle que les prompts la reçoivent. Même format dans l'Edge Function."""
    if not figures:
        return "(no figures available)"
    lines = []
    for f in figures:
        caption = f.caption if len(f.caption) <= CAPTION_CHARS_IN_PROMPT else f.caption[:CAPTION_CHARS_IN_PROMPT] + "…"
        lines.append(f"[{f.label}] {caption}")
    return "\n".join(lines)


def valid_labels(chosen: list[str], figures: list[Figure], limit: int) -> list[str]:
    """Ne garde que les labels qui existent dans la liste extraite, sans doublon, au plus `limit`."""
    known = {f.label for f in figures}
    out: list[str] = []
    for label in chosen:
        label = (label or "").strip().removeprefix("Fig.").removeprefix("Figure").strip(" []")
        if label in known and label not in out:
            out.append(label)
    return out[:limit]


# ---------- conversion et copie ----------


def to_webp(data: bytes, name: str) -> bytes:
    """Convertit une image (PNG, JPEG, SVG, PDF) en WebP, largeur maximale 1400 px."""
    from PIL import Image

    lower = name.lower().split("?")[0]
    if lower.endswith((".svg", ".pdf")):
        import pymupdf

        doc = pymupdf.open(stream=data, filetype="svg" if lower.endswith(".svg") else "pdf")
        page = doc[0]
        zoom = min(4.0, MAX_WIDTH / max(1.0, page.rect.width))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    else:
        img = Image.open(io.BytesIO(data))
        img.load()
    if img.mode in ("RGBA", "LA", "P"):
        # Fond blanc sous la transparence : les figures sont dessinées pour une page claire.
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > MAX_WIDTH:
        img = img.resize((MAX_WIDTH, round(img.height * MAX_WIDTH / img.width)), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "WEBP", quality=WEBP_QUALITY, method=6)
    return out.getvalue()


def copy_figure(
    paper_id: str,
    figure: Figure,
    upload,
    *,
    user_agent: str,
    delay_seconds: float,
    assets: dict[str, bytes] | None = None,
) -> tuple[list[str], int]:
    """Télécharge les images d'une figure, les convertit et les dépose via `upload(chemin, octets)`.

    Renvoie (chemins de stockage, octets déposés). `assets` : fichiers de l'archive LaTeX déjà en mémoire.
    """
    paths: list[str] = []
    total = 0
    with httpx.Client(headers={"User-Agent": user_agent}, timeout=60, follow_redirects=True) as http:
        for i, source in enumerate(figure.images):
            if source.startswith(EPRINT):
                data = (assets or {}).get(source[len(EPRINT) :])
                if data is None:
                    log.warning("figure %s/%s: fichier %s absent de l'archive", paper_id, figure.label, source)
                    continue
            else:
                if paths or i:
                    time.sleep(delay_seconds)  # limites de requêtes d'arXiv
                r = http.get(source)
                if r.status_code != 200:
                    log.warning("figure %s/%s: %s -> HTTP %d", paper_id, figure.label, source, r.status_code)
                    continue
                data = r.content
            try:
                webp = to_webp(data, source)
            except Exception as e:  # image illisible : on garde les autres
                log.warning("figure %s/%s: conversion impossible (%s)", paper_id, figure.label, e)
                continue
            path = f"{paper_id}/{figure.label}-{i + 1}.webp"
            upload(path, webp)
            paths.append(path)
            total += len(webp)
    return paths, total


def sync_figures(
    store, *, user_agent: str, delay_seconds: float, assets: dict[str, dict[str, bytes]] | None = None
) -> tuple[int, int]:
    """Copie dans le stockage les figures choisies qui n'y sont pas encore. Renvoie (figures, octets).

    `assets` : par article, les fichiers de son archive LaTeX déjà en mémoire ; sinon l'archive est
    retéléchargée, une fois par article, pour les figures qui en viennent.
    """
    from .fulltext import read_eprint_assets

    assets = dict(assets or {})
    done = total = 0
    first = True
    for paper_id, figure in store.pending_figures():
        if not first:
            time.sleep(delay_seconds)
        first = False
        if any(s.startswith(EPRINT) for s in figure.images) and paper_id not in assets:
            r = httpx.get(
                f"https://arxiv.org/e-print/{paper_id}", headers={"User-Agent": user_agent}, timeout=120, follow_redirects=True
            )
            assets[paper_id] = read_eprint_assets(r.content) if r.status_code == 200 else {}
            time.sleep(delay_seconds)
        paths, size = copy_figure(
            paper_id, figure, store.upload_figure,
            user_agent=user_agent, delay_seconds=delay_seconds, assets=assets.get(paper_id),
        )
        if paths:
            store.set_figure_stored(paper_id, figure.label, paths)
            done += 1
            total += size
            log.info("figure %s/%s: %d image(s), %d Ko", paper_id, figure.label, len(paths), size // 1024)
        else:
            log.warning("figure %s/%s: aucune image copiée", paper_id, figure.label)
    return done, total
