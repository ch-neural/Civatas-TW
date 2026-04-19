"""VendorRouter and multi-vendor fan-out (spec §B3-B4)."""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from dataclasses import dataclass, field
from typing import Optional

from .client import VendorResponse
from .clients import register_default_clients
from ..storage import db as storage_db


def prompt_hash(system_prompt: str, user_prompt: str) -> str:
    """SHA-256 hex of concatenated prompts (invariant: all vendors must get same)."""
    h = hashlib.sha256()
    h.update(system_prompt.encode("utf-8"))
    h.update(b"\x00")
    h.update(user_prompt.encode("utf-8"))
    return h.hexdigest()


@dataclass
class MultiVendorResult:
    results: dict[str, VendorResponse]
    prompt_hash: str
    experiment_id: str
    persona_id: str
    sim_day: int


class BudgetExceededError(RuntimeError):
    pass


class VendorRouter:
    """Dispatches a prompt to one or many vendors in parallel.

    Per spec §0.2: vendor failures NEVER fallback to another vendor.
    """
    HARD_BUDGET_USD = 400.0     # spec §B5 kill switch

    def __init__(self, clients: Optional[dict] = None):
        self.clients = clients if clients is not None else register_default_clients()

    async def _check_budget(self, experiment_id: str):
        spent = storage_db.total_cost(experiment_id)
        if spent >= self.HARD_BUDGET_USD:
            raise BudgetExceededError(
                f"budget exceeded: spent ${spent:.2f} >= cap ${self.HARD_BUDGET_USD:.2f}"
            )

    async def chat_one(
        self, vendor: str, system_prompt: str, user_prompt: str,
        seed: int, experiment_id: str, persona_id: str, sim_day: int,
        articles_shown: Optional[list] = None,
    ) -> VendorResponse:
        await self._check_budget(experiment_id)
        if vendor not in self.clients:
            raise KeyError(f"unregistered vendor: {vendor}")

        client = self.clients[vendor]
        response = await client.chat(system_prompt, user_prompt, seed)

        # Log to SQLite
        call_id = str(uuid.uuid4())
        ph = prompt_hash(system_prompt, user_prompt)
        storage_db.log_vendor_call(
            call_id=call_id,
            experiment_id=experiment_id,
            persona_id=persona_id,
            sim_day=sim_day,
            vendor=vendor,
            model_id=response.model_id,
            articles_shown=articles_shown or [],
            prompt_hash=ph,
            response=response,
        )
        return response

    async def chat_multivendor(
        self, vendors: list[str], system_prompt: str, user_prompt: str,
        seed: int, experiment_id: str, persona_id: str, sim_day: int,
        articles_shown: Optional[list] = None,
    ) -> MultiVendorResult:
        """Fan out a single prompt to N vendors in parallel. No fallback on failure."""
        ph = prompt_hash(system_prompt, user_prompt)

        async def _one(v: str):
            try:
                return v, await self.chat_one(
                    v, system_prompt, user_prompt, seed,
                    experiment_id, persona_id, sim_day, articles_shown,
                )
            except BudgetExceededError:
                raise  # propagate — kill switch
            except Exception as e:
                # Convert to VendorResponse(status='error'), don't fallback
                return v, VendorResponse(
                    vendor=v, model_id=self.clients.get(v) and self.clients[v].model_id or "",
                    status="error", raw_text="", input_tokens=0, output_tokens=0,
                    error_detail=f"{type(e).__name__}: {e}",
                )

        gathered = await asyncio.gather(*[_one(v) for v in vendors], return_exceptions=False)
        results = {v: r for v, r in gathered}
        return MultiVendorResult(
            results=results, prompt_hash=ph,
            experiment_id=experiment_id, persona_id=persona_id, sim_day=sim_day,
        )
