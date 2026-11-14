"""Étape 4 — Texte complet : HTML arXiv, sinon source LaTeX, sinon PDF, sinon résumé."""

from __future__ import annotations

import gzip
import io
import logging
import re
import tarfile
import time
from dataclasses import dataclass, field
from typing import Literal

import httpx
from bs4 import BeautifulSoup

from .models import Figure, Paper

log = logging.getLogger(__name__)

Source = Literal["html", "latex", "pdf", "abstract"]
MIN_CHARS = 3000  # en dessous, on considère l'extraction comme ratée


def html_to_text(html: str) -> str:
    """Texte de la version HTML d'arXiv (LaTeXML), équations rendues en $LaTeX$."""
    soup = BeautifulSoup(html, "html.parser")
    doc = soup.select_one("article.ltx_document") or soup.body or soup
    for sel in ("nav", "header", "footer", ".ltx_bibliography", ".ltx_page_footer", "script", "style"):
        for el in doc.select(sel):
            el.decompose()
    for math in doc.find_all("math"):
        tex = math.get("alttext") or math.get_text(" ", strip=True)
        display = math.get("display") == "block"
        math.replace_with(f" $${tex}$$ " if display else f"${tex}$")
    # Titres de section marqués « ## » : sert au mode « sections utiles ».
    for h in doc.find_all("h2"):
        h.insert(0, "## ")
    # Saut de ligne après les blocs seulement : le texte en ligne (et ses équations)
    # reste d'un seul tenant.
    for el in doc.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "figcaption", "tr", "br"]):
        el.append("\n\n")
    text = doc.get_text("")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def latex_to_text(files: dict[str, str]) -> str:
    """Fichier .tex principal avec ses \\input, commentaires retirés, à partir de \\begin{document}."""
    mains = [n for n, s in files.items() if "\\documentclass" in s]
    if not mains:
        return ""
    main = max(mains, key=lambda n: len(files[n]))

    def strip_comments(s: str) -> str:
        return re.sub(r"(?<!\\)%.*", "", s)

    def expand(s: str, depth: int = 0) -> str:
        if depth > 5:
            return s

        def repl(m: re.Match) -> str:
            name = m.group(1).strip()
            for cand in (name, name + ".tex"):
                if cand in files:
                    return expand(strip_comments(files[cand]), depth + 1)
            return ""

        return re.sub(r"\\(?:input|include)\{([^}]+)\}", repl, s)

    body = expand(strip_comments(files[main]))
    i = body.find("\\begin{document}")
    body = body[i + len("\\begin{document}") :] if i >= 0 else body
    body = re.split(r"\\begin\{thebibliography\}|\\bibliography\{", body)[0]
    # Titres de section marqués « ## », comme pour le HTML.
    body = body.replace("\\appendix", "\n\n## Appendix\n\n")
    body = re.sub(r"\\section\*?\{([^}]*)\}", r"\n\n## \1\n\n", body)
    return re.sub(r"\n\s*\n+", "\n\n", body).strip()


_USEFUL = re.compile(r"intro|result|discussion|conclu|summary|outlook", re.I)
_RESULTS = re.compile(r"result|discussion", re.I)
_ANNEX = re.compile(
    r"appendi|supplement|^S\d|acknowledg|method|fabrication|setup|data availab|code availab|author contrib|competing",
    re.I,
)


def select_sections(text: str) -> tuple[str, bool]:
    """Garde le début (titre, résumé) et les sections introduction, résultats,
    discussion, conclusion. Renvoie (texte, réduit).

    Beaucoup d'articles nomment leurs sections par sujet (« Model », « Phase diagram »),
    sans section « Results » : on garde alors tout sauf les annexes, méthodes et
    compléments. Si rien n'est retiré, le texte complet est renvoyé tel quel.
    """
    parts = re.split(r"(?m)^## ", text)
    if len(parts) < 3:
        return text, False
    title = lambda s: s.split("\n", 1)[0]  # noqa: E731
    if any(_RESULTS.search(title(s)) for s in parts[1:]):
        kept = [s for s in parts[1:] if _USEFUL.search(title(s))]
    else:
        # Sections nommées par sujet : les résultats sont dans le corps de l'article.
        # On ne retire alors que ce qui est clairement annexe.
        kept = [s for s in parts[1:] if not _ANNEX.search(title(s))]
    if not kept or len(kept) == len(parts) - 1:
        return text, False
    body = "\n\n".join("## " + s.strip() for s in kept)
    return (parts[0].rstrip() + "\n\n" + body).strip(), True


def _read_eprint(data: bytes) -> dict[str, str]:
    """Le e-print d'arXiv est un tar.gz, ou un unique .tex gzippé."""
    files: dict[str, str] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
            for m in tar.getmembers():
                if m.isfile() and m.name.endswith(".tex") and m.size < 5_000_000:
                    f = tar.extractfile(m)
                    if f:
                        files[m.name] = f.read().decode("utf-8", "replace")
    except tarfile.TarError:
        try:
            files["main.tex"] = gzip.decompress(data).decode("utf-8", "replace")
        except OSError:
            pass
    return files


def read_eprint_assets(data: bytes) -> dict[str, bytes]:
    """Images de l'archive LaTeX (pour le repli des figures), par nom de fichier."""
    assets: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
            for m in tar.getmembers():
                if m.isfile() and m.name.lower().endswith((".png", ".jpg", ".jpeg", ".pdf", ".svg")) and m.size < 20_000_000:
                    f = tar.extractfile(m)
                    if f:
                        assets[m.name] = f.read()
    except tarfile.TarError:
        pass
    return assets


def _pdf_to_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages).strip()


@dataclass
class FullText:
    text: str
    source: Source
    truncated: bool = False
    figures: list[Figure] = field(default_factory=list)
    assets: dict[str, bytes] = field(default_factory=dict)  # images de l'archive LaTeX, si c'est la source


def fetch_fulltext(paper: Paper, *, user_agent: str, delay_seconds: float, max_chars: int) -> FullText:
    """Texte complet et figures. Ne lève pas : retombe sur le résumé, sans figure."""
    from .figures import extract_figures_html, extract_figures_latex

    vid = f"{paper.arxiv_id}v{paper.version}"

    def from_html(r: httpx.Response) -> FullText:
        return FullText(html_to_text(r.text), "html", figures=extract_figures_html(r.text, f"https://arxiv.org/html/{vid}"))

    def from_latex(r: httpx.Response) -> FullText:
        text = latex_to_text(_read_eprint(r.content))
        assets = read_eprint_assets(r.content)
        figures = extract_figures_latex(text, list(assets))
        used = {img.removeprefix("eprint:") for f in figures for img in f.images}
        return FullText(text, "latex", figures=figures, assets={k: v for k, v in assets.items() if k in used})

    attempts = (
        ("html", f"https://arxiv.org/html/{vid}", from_html),
        ("latex", f"https://arxiv.org/e-print/{vid}", from_latex),
        ("pdf", f"https://arxiv.org/pdf/{vid}", lambda r: FullText(_pdf_to_text(r.content), "pdf")),
    )
    with httpx.Client(headers={"User-Agent": user_agent}, timeout=60, follow_redirects=True) as client:
        for i, (source, url, extract) in enumerate(attempts):
            if i:
                time.sleep(delay_seconds)
            try:
                r = client.get(url)
                if r.status_code != 200:
                    continue
                full = extract(r)
            except Exception as e:  # réseau, archive ou PDF illisible : on passe à la source suivante
                log.warning("texte complet %s via %s: %s", paper.arxiv_id, source, e)
                continue
            if len(full.text) >= MIN_CHARS:
                full.truncated = len(full.text) > max_chars
                if full.truncated:
                    log.warning("texte complet %s: coupé à %d caractères", paper.arxiv_id, max_chars)
                full.text = full.text[:max_chars]
                return full
    return FullText(paper.abstract, "abstract")
