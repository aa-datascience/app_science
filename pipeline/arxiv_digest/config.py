"""Chargement de config.yaml (réglages) — les secrets viennent de .env."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]


class EditionCfg(BaseModel):
    size: int = 8
    max_per_category: int = 3
    exploration_slots: int = 1


class CategoriesCfg(BaseModel):
    followed: dict[str, float]
    exploration: list[str] = []


class PrefilterCfg(BaseModel):
    max_candidates: int = 100
    max_exploration_candidates: int = 15
    keywords_positive: dict[str, float] = {}
    keywords_negative: dict[str, float] = {}
    followed_authors: list[str] = []
    author_bonus: float = 2.0


class ScoringCfg(BaseModel):
    weights: dict[str, float] = Field(
        default_factory=lambda: {"relevance": 0.4, "importance": 0.3, "novelty": 0.2, "prefilter": 0.1}
    )


class ProfileCfg(BaseModel):
    interests: str = ""
    levels: dict[str, str] = {}


class ModelsCfg(BaseModel):
    rank: str = "claude-haiku-5-5"
    card: str = "claude-haiku-5-5"
    generate: str = "claude-opus-5-5"
    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    rank_batch_size: int = 25


class BudgetCfg(BaseModel):
    monthly_usd: float = 15.0
    # modèle -> [entrée, sortie] ou [entrée, sortie, lecture de cache], USD par million de tokens
    prices: dict[str, list[float]] = {}
    assumed_tokens: dict[str, tuple[int, int]] = {"card": (800, 1500), "detail": (30_000, 6000)}


class BatchCfg(BaseModel):
    poll_seconds: float = 60
    timeout_minutes: float = 300


class FulltextCfg(BaseModel):
    mode: Literal["full", "sections"] = "full"


class ArxivCfg(BaseModel):
    user_agent: str = "arxiv-digest-pipeline/0.1"
    delay_seconds: float = 3.0
    max_fulltext_chars: int = 300_000


class Config(BaseModel):
    edition: EditionCfg = EditionCfg()
    categories: CategoriesCfg
    prefilter: PrefilterCfg = PrefilterCfg()
    scoring: ScoringCfg = ScoringCfg()
    profile: ProfileCfg = ProfileCfg()
    models: ModelsCfg = ModelsCfg()
    budget: BudgetCfg = BudgetCfg()
    batch: BatchCfg = BatchCfg()
    fulltext: FulltextCfg = FulltextCfg()
    arxiv: ArxivCfg = ArxivCfg()


def load_config(path: Path | None = None) -> Config:
    path = path or REPO_ROOT / "config.yaml"
    return Config.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
