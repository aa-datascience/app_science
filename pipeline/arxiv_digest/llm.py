"""Appels à l'API Claude : sortie validée par schéma, suivi du coût, plafond quotidien."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from .config import Config

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class BudgetExceeded(Exception):
    """Le plafond de dépense quotidien est atteint."""


class LLMRefused(Exception):
    """Le modèle a refusé la requête (stop_reason == "refusal")."""


class LLMInvalid(Exception):
    """Pas de sortie conforme au schéma après les nouvelles tentatives."""


class LLM:
    def __init__(self, cfg: Config, usage_log: Path, day: str, client: anthropic.Anthropic | None = None):
        self.cfg = cfg
        self.usage_log = usage_log
        self.day = day
        # max_retries : le SDK relance seul les erreurs réseau, 429 et 5xx.
        self.client = client or anthropic.Anthropic(max_retries=4)
        self.spent = self._spent_on(day)

    def _spent_on(self, day: str) -> float:
        if not self.usage_log.exists():
            return 0.0
        total = 0.0
        for line in self.usage_log.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row["date"] == day:
                total += row["cost_usd"]
        return total

    def cost(self, model: str, usage) -> float:
        """Coût estimé en USD (écriture de cache ×1,25, lecture ×0,1)."""
        if model not in self.cfg.budget.prices:
            log.warning("pas de prix pour %s dans config.yaml : coût compté à 0", model)
            return 0.0
        p_in, p_out = self.cfg.budget.prices[model]
        tokens_in = (
            usage.input_tokens
            + 1.25 * (getattr(usage, "cache_creation_input_tokens", 0) or 0)
            + 0.1 * (getattr(usage, "cache_read_input_tokens", 0) or 0)
        )
        return (tokens_in * p_in + usage.output_tokens * p_out) / 1_000_000

    def _record(self, step: str, model: str, usage) -> None:
        cost = self.cost(model, usage)
        self.spent += cost
        row = {
            "date": self.day,
            "step": step,
            "model": model,
            "input_tokens": usage.input_tokens,
            "cache_write_tokens": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "output_tokens": usage.output_tokens,
            "cost_usd": round(cost, 6),
        }
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)
        with self.usage_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        log.info("%s [%s] in=%d out=%d coût=%.4f$ (jour: %.3f$)", step, model, usage.input_tokens, usage.output_tokens, cost, self.spent)

    def parse(
        self,
        *,
        step: str,
        model: str,
        system: str,
        content: list[dict] | str,
        schema: type[T],
        max_tokens: int = 16000,
        attempts: int = 2,
    ) -> T:
        """Un appel dont la sortie est validée par `schema` ; nouvelle tentative si invalide."""
        for attempt in range(1, attempts + 1):
            if self.spent >= self.cfg.budget.daily_usd:
                raise BudgetExceeded(f"{self.spent:.3f}$ dépensés, plafond {self.cfg.budget.daily_usd}$")
            try:
                resp = self.client.messages.parse(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": content}],
                    output_format=schema,
                    output_config={"effort": self.cfg.models.effort},
                )
            except ValidationError as e:
                log.warning("%s: JSON invalide (tentative %d/%d): %s", step, attempt, attempts, e)
                continue
            self._record(step, model, resp.usage)
            if resp.stop_reason == "refusal":
                raise LLMRefused(step)
            if resp.stop_reason == "max_tokens" or resp.parsed_output is None:
                log.warning("%s: sortie incomplète (%s), tentative %d/%d", step, resp.stop_reason, attempt, attempts)
                continue
            return resp.parsed_output
        raise LLMInvalid(step)
