"""Appels à l'API Claude : sortie validée par schéma, suivi du coût, mode synchrone ou Batches."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from pydantic import BaseModel, ValidationError

from .config import Config

log = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """Le plafond fixé pour cette exécution est atteint."""


class LLMRefused(Exception):
    """Le modèle a refusé la requête (stop_reason == "refusal")."""


class LLMInvalid(Exception):
    """Pas de sortie conforme au schéma."""


class BatchFailed(Exception):
    """Le lot n'a pas abouti (délai dépassé, requête en erreur ou expirée)."""


@dataclass
class Req:
    step: str
    model: str
    system: str
    content: list[dict] | str
    schema: type[BaseModel]
    tag: dict = field(default_factory=dict)  # arxiv_id, label, mode : recopiés dans le journal
    max_tokens: int = 16000


def read_usage(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def usage_cost(prices: list[float], row: dict) -> float:
    """Coût en USD d'une ligne du journal.

    Écriture de cache : x1,25 (5 min) ou x2 (1 h). Lecture de cache : prix dédié,
    sinon 10 % du prix d'entrée. Batches : -50 % sur tout.
    """
    p_in, p_out = prices[0], prices[1]
    p_read = prices[2] if len(prices) > 2 else 0.1 * p_in
    usd = (
        row["input_tokens"] * p_in
        + row["cache_write_5m_tokens"] * 1.25 * p_in
        + row["cache_write_1h_tokens"] * 2 * p_in
        + row["cache_read_tokens"] * p_read
        + row["output_tokens"] * p_out
    ) / 1_000_000
    return usd * (0.5 if row.get("batch") else 1.0)


class LLM:
    def __init__(
        self,
        cfg: Config,
        usage_log: Path | Callable[[dict], None],
        day: str,
        client: anthropic.Anthropic | None = None,
        hard_cap_usd: float | None = None,
    ):
        self.cfg = cfg
        self.usage_log = usage_log
        self.day = day
        # max_retries : le SDK relance seul les erreurs réseau, 429 et 5xx.
        self.client = client or anthropic.Anthropic(max_retries=4)
        self.hard_cap_usd = hard_cap_usd
        self.run_spent = 0.0
        self.records: list[dict] = []

    # ---------- construction de la requête ----------

    def _params(self, req: Req) -> dict:
        return {
            "model": req.model,
            "max_tokens": req.max_tokens,
            "system": req.system,
            "messages": [{"role": "user", "content": req.content}],
            "output_config": {
                "effort": self.cfg.models.effort,
                "format": {"type": "json_schema", "schema": anthropic.transform_schema(req.schema)},
            },
        }

    # ---------- journal des coûts ----------

    def _record(self, req: Req, usage, *, batch: bool) -> None:
        creation = getattr(usage, "cache_creation", None)
        w1h = getattr(creation, "ephemeral_1h_input_tokens", 0) or 0
        w_all = getattr(usage, "cache_creation_input_tokens", 0) or 0
        row = {
            "date": self.day,
            "step": req.step,
            "model": req.model,
            "batch": batch,
            **req.tag,
            "input_tokens": usage.input_tokens,
            "cache_write_5m_tokens": max(0, w_all - w1h),
            "cache_write_1h_tokens": w1h,
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "output_tokens": usage.output_tokens,
        }
        prices = self.cfg.budget.prices.get(req.model)
        if prices is None:
            log.warning("pas de prix pour %s dans config.yaml : coût compté à 0", req.model)
        row["cost_usd"] = round(usage_cost(prices, row), 6) if prices else 0.0
        self.run_spent += row["cost_usd"]
        self.records.append(row)
        if callable(self.usage_log):  # stockage (fichier local ou base) fourni par l'appelant
            self.usage_log(row)
        else:
            self.usage_log.parent.mkdir(parents=True, exist_ok=True)
            with self.usage_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
        log.info(
            "%s [%s%s] in=%d cache(w=%d r=%d) out=%d coût=%.4f$",
            req.step,
            req.model,
            ", batch" if batch else "",
            row["input_tokens"],
            w_all,
            row["cache_read_tokens"],
            row["output_tokens"],
            row["cost_usd"],
        )

    def _check_cap(self) -> None:
        if self.hard_cap_usd is not None and self.run_spent >= self.hard_cap_usd:
            raise BudgetExceeded(f"{self.run_spent:.3f}$ dépensés, plafond {self.hard_cap_usd}$")

    def _parse(self, req: Req, message) -> BaseModel:
        if message.stop_reason == "refusal":
            raise LLMRefused(req.step)
        if message.stop_reason == "max_tokens":
            raise LLMInvalid(f"{req.step}: sortie coupée (max_tokens)")
        text = next((b.text for b in message.content if b.type == "text"), None)
        if text is None:
            raise LLMInvalid(f"{req.step}: pas de texte dans la réponse")
        try:
            return req.schema.model_validate_json(text)
        except ValidationError as e:
            raise LLMInvalid(f"{req.step}: JSON invalide ({e.error_count()} erreurs)") from e

    # ---------- mode synchrone ----------

    def run(self, req: Req, attempts: int = 2) -> BaseModel:
        """Un appel ; nouvelle tentative si la sortie est invalide."""
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            self._check_cap()
            message = self.client.messages.create(**self._params(req))
            self._record(req, message.usage, batch=False)
            try:
                return self._parse(req, message)
            except LLMInvalid as e:
                log.warning("%s (tentative %d/%d)", e, attempt, attempts)
                last = e
        raise last  # type: ignore[misc]

    # ---------- mode Batches (-50 %, asynchrone) ----------

    def run_batch(self, reqs: list[Req]) -> list[BaseModel | Exception]:
        """Envoie les requêtes en un lot et attend la fin. Un résultat ou une exception par requête."""
        if not reqs:
            return []
        self._check_cap()
        batch = self.client.messages.batches.create(
            requests=[{"custom_id": f"r{i}", "params": self._params(r)} for i, r in enumerate(reqs)]
        )
        log.info("lot %s envoyé: %d requêtes (%s)", batch.id, len(reqs), reqs[0].step)
        deadline = time.monotonic() + self.cfg.batch.timeout_minutes * 60
        while batch.processing_status != "ended":
            if time.monotonic() > deadline:
                self.client.messages.batches.cancel(batch.id)
                raise BatchFailed(f"lot {batch.id}: délai de {self.cfg.batch.timeout_minutes} min dépassé, annulé")
            time.sleep(self.cfg.batch.poll_seconds)
            batch = self.client.messages.batches.retrieve(batch.id)

        out: list[BaseModel | Exception] = [BatchFailed("résultat absent")] * len(reqs)
        # Les résultats arrivent dans un ordre quelconque : on se fie au custom_id.
        for entry in self.client.messages.batches.results(batch.id):
            i = int(entry.custom_id[1:])
            if entry.result.type != "succeeded":
                out[i] = BatchFailed(f"{reqs[i].step}: {entry.result.type}")
                continue
            self._record(reqs[i], entry.result.message.usage, batch=True)
            try:
                out[i] = self._parse(reqs[i], entry.result.message)
            except (LLMInvalid, LLMRefused) as e:
                out[i] = e
        return out
