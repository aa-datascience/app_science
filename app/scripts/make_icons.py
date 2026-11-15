"""Génère les icônes de l'app (assets/*.png) à partir d'un seul dessin SVG.

Le dessin : une page à coin replié (une édition, finie) portant une oscillation amortie et deux
lignes de texte. Couleurs de `src/lib/theme.ts`.

Lancement, depuis la racine du dépôt :
    pipeline/.venv/Scripts/python app/scripts/make_icons.py
"""

import io
import math
from pathlib import Path

import resvg_py
from PIL import Image

ASSETS = Path(__file__).resolve().parents[1] / "assets"
BG, ACCENT, MUTED = "#0e0f11", "#c9b98a", "#8e8c86"


def wave() -> str:
    # Oscillation amortie : y = A e^(-k t) sin(2 pi f t), t de 0 à 1.
    pts = []
    for i in range(121):
        t = i / 120
        x = 392 + 240 * t
        y = 478 - 62 * math.exp(-2.0 * t) * math.sin(2 * math.pi * 2.5 * t)
        pts.append(f"{x:.1f},{y:.1f}")
    return "M" + " L".join(pts)


def symbol(main: str, second: str) -> str:
    """Page centrée dans un carré de 1024, contenue dans la zone sûre des icônes adaptatives."""
    page = "M372 282 H602 L692 372 V702 Q692 742 652 742 H372 Q332 742 332 702 V322 Q332 282 372 282 Z"
    fold = "M602 282 V340 Q602 372 634 372 H692"
    s = f'stroke-linecap="round" stroke-linejoin="round" fill="none"'
    return (
        f'<path d="{page}" stroke="{main}" stroke-width="28" {s}/>'
        f'<path d="{fold}" stroke="{main}" stroke-width="28" {s}/>'
        f'<path d="{wave()}" stroke="{main}" stroke-width="24" {s}/>'
        f'<path d="M392 604 H632 M392 664 H552" stroke="{second}" stroke-width="24" {s}/>'
    )


def svg(body: str, background: str | None = None) -> str:
    bg = f'<rect width="1024" height="1024" fill="{background}"/>' if background else ""
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1024" viewBox="0 0 1024 1024">{bg}{body}</svg>'


def render(source: str, name: str, size: int = 1024) -> None:
    png = resvg_py.svg_to_bytes(svg_string=source, width=size, height=size)
    img = Image.open(io.BytesIO(bytes(png)))
    img.save(ASSETS / name, optimize=True)
    print(name, img.size)


def main() -> None:
    render(svg(symbol(ACCENT, MUTED), BG), "icon.png")
    render(svg(symbol(ACCENT, MUTED)), "android-icon-foreground.png")
    render(svg("", BG), "android-icon-background.png")
    # Monochrome (icônes à thème d'Android 13+) : une seule couleur, le système teinte.
    render(svg(symbol("#ffffff", "#ffffff")), "android-icon-monochrome.png")
    render(svg(symbol(ACCENT, MUTED)), "splash-icon.png")
    render(svg(symbol(ACCENT, MUTED), BG), "favicon.png", 48)
    (ASSETS / "icon.svg").write_text(svg(symbol(ACCENT, MUTED), BG), encoding="utf-8")


if __name__ == "__main__":
    main()
