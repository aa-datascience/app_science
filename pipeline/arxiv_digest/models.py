"""Schémas Pydantic : données arXiv, sorties des modèles (spec §5), édition."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

# ---------- arXiv ----------


class Paper(BaseModel):
    arxiv_id: str
    version: int = 1
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    announce_type: str = "new"  # new | cross | replace | replace-cross
    published: str = ""

    @property
    def primary_category(self) -> str:
        return self.categories[0] if self.categories else ""

    @property
    def abs_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

    @property
    def pdf_url(self) -> str:
        return f"https://arxiv.org/pdf/{self.arxiv_id}"


class Candidate(BaseModel):
    paper: Paper
    prefilter_score: float
    slot: Literal["main", "exploration"] = "main"


# ---------- Classement (sortie du modèle rapide) ----------


def _clamp(v: int) -> int:
    return max(1, min(5, int(v)))


class RankItem(BaseModel):
    arxiv_id: str
    relevance: int = Field(description="1-5: fit with the reader's interests")
    importance: int = Field(description="1-5: significance of the result for its field")
    novelty: int = Field(description="1-5: how new the idea or result is")
    difficulty: int = Field(description="1-5: background needed to follow it")
    why: str = Field(description="One sentence: why this paper for this reader")

    _c = field_validator("relevance", "importance", "novelty", "difficulty")(_clamp)


class RankBatch(BaseModel):
    items: list[RankItem]


class Ranked(BaseModel):
    candidate: Candidate
    rank: RankItem
    final_score: float = 0.0


# ---------- Figures ----------


class Figure(BaseModel):
    """Une figure extraite de l'article : de quoi laisser un modèle choisir, et retrouver l'image."""

    label: str  # « 1 », « 2 », « S1 »… tel qu'imprimé dans l'article
    caption: str  # légende complète, LaTeX conservé
    images: list[str]  # adresses d'origine (sous-figures comprises) ; « eprint:fichier » pour la source LaTeX


class StoredFigure(Figure):
    """Une figure telle qu'elle est stockée, avec son rôle une fois choisie."""

    roles: list[Literal["card", "detail"]] = []
    what_to_look_at: str = ""
    storage_paths: list[str] = []  # images WebP copiées dans le stockage (figures choisies seulement)
    stored: bool = False


# ---------- Contenu généré ----------


class Card(BaseModel):
    """Carte générée la nuit, à partir du titre et du résumé seulement."""

    plain_title: str = Field(description="Title rewritten in plain language")
    finding: str = Field(description="One sentence: what they found")
    why_it_matters: str = Field(description="One sentence: why it matters")
    tags: list[str]
    difficulty: int = Field(description="1-5")
    figure: str = Field(description="Label of the one figure that best illustrates the main result, or an empty string")

    _c = field_validator("difficulty")(_clamp)


class Context(BaseModel):
    before: str = Field(description="What was known before this paper")
    change: str = Field(description="What this paper changes")
    limitations: str = Field(description="Limitations and possible criticisms (mandatory)")


class Claim(BaseModel):
    statement: str = Field(description="A factual claim made in the entry")
    quote: str = Field(description="Passage copied character for character from the paper, supporting the claim")


class FigureNote(BaseModel):
    label: str = Field(description="Label of a figure from the list given, exactly as written there")
    what_to_look_at: str = Field(description="One sentence telling the reader what to notice in this figure")


class Detail(BaseModel):
    """Détail généré à l'ouverture d'un article, à partir du texte complet."""

    explanation_lay: str = Field(description="150-250 words, educated layperson, no formulas")
    explanation_expert: str = Field(description="300-500 words, physics master's level, LaTeX in $...$ / $$...$$")
    context: Context
    claims: list[Claim]
    figures: list[FigureNote] = Field(description="One to three figures that best support the explanation; empty if none is listed")


class StoredDetail(BaseModel):
    """Détail tel qu'il est stocké : généré une fois, jamais régénéré."""

    arxiv_id: str
    detail: Detail  # ses claims sont celles dont la citation a été retrouvée dans l'article
    removed_claims: list[Claim] = []  # citations introuvables : affirmations retirées
    verification_status: Literal["verified", "unverified"]
    text_source: Literal["html", "latex", "pdf", "abstract"]
    based_on_abstract: bool
    text_truncated: bool = False
    text_mode: Literal["full", "sections"] = "full"
    model: str
    prompt_version: str


# ---------- Édition ----------


class EditionItem(BaseModel):
    position: int
    slot: Literal["main", "exploration"]
    paper: Paper
    rank: RankItem
    final_score: float
    card: Card
    model: str
    prompt_version: str


class Edition(BaseModel):
    date: str
    status: Literal["ready", "failed", "fallback"]
    items: list[EditionItem]
    cost_usd: float = 0.0
    notes: list[str] = []
