"""Figures : extraction sur des articles HTML enregistrés, repli LaTeX, choix, conversion, copie."""

import io
from pathlib import Path

import pytest
from PIL import Image
from test_llm import FakeClient, GOOD, TEXT, make_llm
from test_pipeline import paper

from arxiv_digest.figures import (
    EPRINT,
    copy_figure,
    extract_figures_html,
    extract_figures_latex,
    figures_for_prompt,
    sync_figures,
    to_webp,
    valid_labels,
)
from arxiv_digest.models import Card, Detail, Figure, FigureNote
from arxiv_digest.steps import Article, generate_detail, make_cards
from arxiv_digest.store import LocalStore

HTML = Path(__file__).parent / "fixtures" / "html"


def figures_of(arxiv_vid: str) -> list[Figure]:
    html = (HTML / f"{arxiv_vid}.html").read_text(encoding="utf-8")
    return extract_figures_html(html, f"https://arxiv.org/html/{arxiv_vid}")


def png(width=800, height=600, color="navy") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (width, height), color).save(out, "PNG")
    return out.getvalue()


# ---------- extraction HTML, sur quatre articles réels ----------


def test_html_png_figures_with_latex_captions():
    figs = figures_of("2611.17001v1")
    assert [f.label for f in figs] == ["1", "2", "3"]
    assert figs[0].images == ["https://arxiv.org/html/2611.17001v1/Fig1.png"]
    assert figs[0].caption.startswith("Reflectionless states of a Majorana wire.")
    assert "Figure 1" not in figs[0].caption  # l'étiquette n'est pas répétée dans la légende
    assert all("$" in f.caption for f in figs)  # le LaTeX des légendes est conservé


def test_html_svg_figures_and_multi_image_figures():
    figs = figures_of("2611.14637v1")
    assert [f.label for f in figs] == ["1", "2", "3", "4", "S1"]
    assert figs[0].images == ["https://arxiv.org/html/2611.14637v1/phase_diagram_nice.svg"]  # <object>, pas <img>
    assert r"$\mu_{\alpha}(2i\pi/\beta)$" in figs[0].caption
    assert len(figs[1].images) == 4 and len(set(figs[1].images)) == 4


def test_html_subfigure_panels_are_one_figure():
    figs = {f.label: f for f in figures_of("2611.15872v1")}
    assert len(figs["2"].images) == 6  # six panneaux, une seule figure, une seule légende
    assert figs["2"].caption.startswith("Top row:")
    assert all(len(f.images) == 1 for label, f in figs.items() if label != "2")


def test_html_supplementary_labels_and_tables_ignored():
    figs = figures_of("2611.16705v1")
    assert [f.label for f in figs] == ["1", "2", "3", "4", "5", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
    assert "(a)" in figs[0].caption.replace("( a )", "(a)")
    # Les tableaux (figure.ltx_table) ne sont pas des figures.
    assert len(figures_of("2611.14637v1")) == 5


def test_html_ignores_decorative_and_captionless_figures():
    html = """<article class="ltx_document">
      <figure class="ltx_figure"><img class="ltx_graphics" src="x/logo.png" width="40" height="40"/>
        <figcaption><span class="ltx_tag">Figure 1: </span>The logo of the collaboration, shown small.</figcaption></figure>
      <figure class="ltx_figure"><img class="ltx_graphics" src="x/orcid.png" width="400" height="300"/></figure>
      <figure class="ltx_figure"><img class="ltx_graphics" src="x/short.png" width="400" height="300"/>
        <figcaption><span class="ltx_tag">Figure 2: </span>Logo.</figcaption></figure>
      <figure class="ltx_figure"><img class="ltx_graphics" src="x/ok.png" width="400" height="300"/>
        <figcaption><span class="ltx_tag">Figure 3: </span>Conductance versus gate voltage at base temperature.</figcaption></figure>
    </article>"""
    assert [f.label for f in extract_figures_html(html, "https://arxiv.org/html/x")] == ["3"]


# ---------- repli : source LaTeX ----------


def test_latex_figures_resolve_files_and_keep_caption():
    tex = r"""
    \begin{figure}\includegraphics[width=\linewidth]{figs/phase}\caption{Phase diagram with $T_c$ \textbf{versus} doping. \label{f1}}\end{figure}
    \begin{figure*}\includegraphics{a.eps}\includegraphics{b}\caption[short]{Two panels: (a) raw data, (b) the fit.}\end{figure*}
    \begin{figure}\includegraphics{missing}\caption{A figure whose file is not in the archive.}\end{figure}
    """
    figs = extract_figures_latex(tex, ["figs/phase.pdf", "a.eps", "b.png", "main.tex"])
    assert [(f.label, f.images) for f in figs] == [("1", [EPRINT + "figs/phase.pdf"]), ("2", [EPRINT + "b.png"])]
    assert figs[0].caption == r"Phase diagram with $T_c$ \textbf{versus} doping."


# ---------- choix par les modèles ----------


def test_prompt_listing_and_label_validation():
    figs = [Figure(label="1", caption="A" * 900, images=["u"]), Figure(label="S1", caption="short caption", images=["u"])]
    text = figures_for_prompt(figs)
    assert text.splitlines()[0].startswith("[1] AAAA") and text.splitlines()[0].endswith("…")
    assert text.splitlines()[1] == "[S1] short caption"
    assert figures_for_prompt([]) == "(no figures available)"
    assert valid_labels(["2", "S1", "[1]", "S1", "Fig. 1"], figs, 3) == ["S1", "1"]  # inconnus et doublons écartés
    assert valid_labels(["1", "S1"], figs, 1) == ["1"]
    assert valid_labels([""], figs, 1) == []


def test_card_figure_must_exist_in_extracted_list(cfg, tmp_path):
    class Client(FakeClient):
        def __init__(self, label):
            super().__init__()
            self.label = label

        def _answer(self, params):
            msg = super()._answer(params)
            card = Card.model_validate_json(msg.content[0].text).model_copy(update={"figure": self.label})
            msg.content[0].text = card.model_dump_json()
            return msg

    figs = {"2611.00001": [Figure(label="2", caption="Main result plot of the paper.", images=["u"])]}
    for label, expected in (("2", "2"), ("7", ""), ("", "")):
        client = Client(label)
        cards, _ = make_cards(make_llm(cfg, tmp_path, client), [paper(1)], cfg, batch=False, figures=figs)
        assert cards["2611.00001"].figure == expected
        assert "[2] Main result plot of the paper." in client.calls[0]["messages"][0]["content"]


def test_detail_keeps_at_most_three_existing_figures(cfg, tmp_path):
    class Client(FakeClient):
        def _answer(self, params):
            msg = super()._answer(params)
            notes = [FigureNote(label=x, what_to_look_at=f"look at {x}") for x in ("3", "9", "1", "2", "4")]
            detail = Detail.model_validate_json(msg.content[0].text).model_copy(update={"figures": notes})
            msg.content[0].text = detail.model_dump_json()
            return msg

    figs = [Figure(label=str(i), caption=f"Caption of figure number {i}.", images=["u"]) for i in (1, 2, 3, 4)]
    client = Client(quotes=[GOOD])
    stored = generate_detail(make_llm(cfg, tmp_path, client), Article(paper(1), TEXT, "html", figures=figs), cfg)
    assert [(f.label, f.what_to_look_at) for f in stored.detail.figures] == [
        ("3", "look at 3"), ("1", "look at 1"), ("2", "look at 2"),
    ]
    assert "[4] Caption of figure number 4." in client.calls[0]["messages"][0]["content"][1]["text"]


# ---------- conversion et copie ----------


def test_to_webp_resizes_and_flattens_transparency():
    out = Image.open(io.BytesIO(to_webp(png(2800, 1000), "big.png")))
    assert out.format == "WEBP" and out.size == (1400, 500)
    assert Image.open(io.BytesIO(to_webp(png(600, 400), "small.png"))).size == (600, 400)  # jamais agrandie

    buf = io.BytesIO()
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(buf, "PNG")
    flat = Image.open(io.BytesIO(to_webp(buf.getvalue(), "t.png"))).convert("RGB")
    assert flat.getpixel((10, 10))[0] > 240  # transparent -> fond blanc, pas noir


def test_to_webp_renders_svg_and_pdf():
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="red"/></svg>'
    img = Image.open(io.BytesIO(to_webp(svg, "https://arxiv.org/html/x/plot.svg")))
    assert img.format == "WEBP" and img.width >= 200 and img.convert("RGB").getpixel((img.width // 2, img.height // 2))[0] > 200

    import pymupdf

    doc = pymupdf.open()
    doc.new_page(width=300, height=200)
    assert Image.open(io.BytesIO(to_webp(doc.tobytes(), "figs/phase.pdf"))).format == "WEBP"


def test_copy_figure_from_latex_assets_and_skips_unreadable():
    uploads = {}
    fig = Figure(label="2", caption="c", images=[EPRINT + "a.png", EPRINT + "broken.png", EPRINT + "absent.png"])
    paths, size = copy_figure(
        "2611.00001", fig, uploads.__setitem__, user_agent="t", delay_seconds=0,
        assets={"a.png": png(), "broken.png": b"not an image"},
    )
    assert paths == ["2611.00001/2-1.webp"] and list(uploads) == paths and size == len(uploads[paths[0]])


def test_only_chosen_figures_are_copied(tmp_path):
    store = LocalStore(tmp_path)
    figs = [Figure(label=str(i), caption=f"Caption {i} of the paper.", images=[EPRINT + f"{i}.png"]) for i in (1, 2, 3)]
    store.save_figures("2611.00001", figs)
    assert sync_figures(store, user_agent="t", delay_seconds=0) == (0, 0)  # rien de choisi : rien de copié

    store.mark_figures("2611.00001", "card", {"2": ""})
    store.mark_figures("2611.00001", "detail", {"2": "the dip at zero bias", "3": "the slope"})
    assets = {"2611.00001": {"2.png": png(), "3.png": png()}}
    n, size = sync_figures(store, user_agent="t", delay_seconds=0, assets=assets)
    assert n == 2 and size > 0
    by_label = {f.label: f for f in store.get_figures("2611.00001")}
    assert by_label["2"].roles == ["card", "detail"] and by_label["2"].what_to_look_at == "the dip at zero bias"
    assert by_label["2"].stored and by_label["2"].storage_paths == ["2611.00001/2-1.webp"]
    assert not by_label["1"].stored and by_label["1"].roles == []
    assert sorted(p.name for p in (tmp_path / "figures" / "2611.00001").iterdir()) == ["2-1.webp", "3-1.webp"]
    assert sync_figures(store, user_agent="t", delay_seconds=0, assets=assets) == (0, 0)  # déjà copiées

    store.save_figures("2611.00001", figs)  # une nouvelle extraction ne fait pas perdre les rôles
    assert {f.label: f.stored for f in store.get_figures("2611.00001")} == {"1": False, "2": True, "3": True}
