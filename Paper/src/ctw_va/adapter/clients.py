"""5 concrete vendor clients — all use OpenAI SDK against vendor-specific endpoints."""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError as OpenAIRateLimitError
from openai._exceptions import AuthenticationError as OpenAIAuthError

from .client import (
    VendorClient, VendorResponse, CANONICAL_GEN_CONFIG,
    RateLimitError, TransientServerError, AuthError, TimeoutError_,
    ContentFilterError,
)
from ..data.pricing import estimate_cost


def _map_error(e: Exception) -> Exception:
    """Normalize OpenAI SDK errors to our taxonomy."""
    if isinstance(e, OpenAIRateLimitError):
        return RateLimitError(str(e))
    if isinstance(e, OpenAIAuthError):
        return AuthError(str(e))
    if isinstance(e, APITimeoutError):
        return TimeoutError_(str(e))
    msg = str(e).lower()
    if "content" in msg and "filter" in msg:
        return ContentFilterError(str(e))
    if isinstance(e, APIError):
        return TransientServerError(str(e))
    return e


class _OpenAICompatibleClient(VendorClient):
    """Shared logic for vendors using OpenAI-compatible endpoints."""
    base_url: Optional[str] = None       # subclass may override
    extra_body: Optional[dict] = None    # subclass may override

    def _build_client(self) -> AsyncOpenAI:
        kwargs: dict = {"api_key": self.api_key, "timeout": 60.0}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return AsyncOpenAI(**kwargs)

    async def chat(self, system_prompt: str, user_prompt: str, seed: int) -> VendorResponse:
        client = self._build_client()
        t0 = time.monotonic()
        attempt = 0

        for attempt_num in range(4):
            attempt = attempt_num + 1
            try:
                kwargs = {
                    **CANONICAL_GEN_CONFIG,
                    "model": self.model_id,
                    "seed": seed,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                if self.extra_body:
                    kwargs["extra_body"] = self.extra_body

                resp = await client.chat.completions.create(**kwargs)
                latency_ms = int((time.monotonic() - t0) * 1000)

                msg = resp.choices[0].message.content or ""
                usage = resp.usage
                in_tok = getattr(usage, "prompt_tokens", 0) or 0
                out_tok = getattr(usage, "completion_tokens", 0) or 0
                cached = getattr(usage, "prompt_cache_hit_tokens", 0) or 0
                cost = estimate_cost(self.vendor_name, in_tok, out_tok, cached)

                return VendorResponse(
                    vendor=self.vendor_name,
                    model_id=self.model_id,
                    status="ok",
                    raw_text=msg,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cached_tokens=cached,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    finish_reason=resp.choices[0].finish_reason or "",
                    system_fingerprint=getattr(resp, "system_fingerprint", None),
                    attempt=attempt,
                )
            except ContentFilterError as e:
                return VendorResponse(
                    vendor=self.vendor_name,
                    model_id=self.model_id,
                    status="refusal_filter",
                    raw_text="",
                    input_tokens=0, output_tokens=0,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error_detail=str(e),
                    attempt=attempt,
                )
            except Exception as e:
                mapped = _map_error(e)
                if isinstance(mapped, (RateLimitError, TransientServerError, TimeoutError_)):
                    if attempt_num < 3:
                        import random
                        await asyncio.sleep((2 ** attempt_num) + random.random() * 0.5)
                        continue
                # Final failure or unrecoverable error
                return VendorResponse(
                    vendor=self.vendor_name,
                    model_id=self.model_id,
                    status="error",
                    raw_text="",
                    input_tokens=0, output_tokens=0,
                    latency_ms=int((time.monotonic() - t0) * 1000),
                    error_detail=f"{type(mapped).__name__}: {mapped}",
                    attempt=attempt,
                )

        # Should not reach here
        return VendorResponse(
            vendor=self.vendor_name,
            model_id=self.model_id,
            status="error",
            raw_text="",
            input_tokens=0, output_tokens=0,
            error_detail="retry attempts exhausted",
            attempt=attempt,
        )


class OpenAIClient(_OpenAICompatibleClient):
    vendor_name = "openai"
    model_id = "gpt-4o-mini"
    base_url = None   # default OpenAI endpoint
    def _env_key(self): return "OPENAI_API_KEY"


class GeminiClient(_OpenAICompatibleClient):
    vendor_name = "gemini"
    model_id = "gemini-2.5-flash-lite"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
    extra_body = {"generationConfig": {"thinkingBudget": 0}}  # disable reasoning
    def _env_key(self): return "GEMINI_API_KEY"


class GrokClient(_OpenAICompatibleClient):
    vendor_name = "grok"
    model_id = "grok-4.1-fast"   # non-reasoning variant per spec
    base_url = "https://api.x.ai/v1"
    def _env_key(self): return "XAI_API_KEY"


class DeepSeekClient(_OpenAICompatibleClient):
    vendor_name = "deepseek"
    model_id = "deepseek-chat"    # V3.2, non-reasoner per spec
    base_url = "https://api.deepseek.com/v1"
    def _env_key(self): return "DEEPSEEK_API_KEY"


class KimiClient(_OpenAICompatibleClient):
    vendor_name = "kimi"
    model_id = "kimi-k2-0905"
    base_url = "https://api.moonshot.ai/v1"   # International (.ai), not .cn
    extra_body = {"thinking": {"type": "disabled"}}   # disable reasoning
    def _env_key(self): return "MOONSHOT_API_KEY"


_REGISTRY: dict = {}


def register_default_clients() -> dict:
    """Instantiate all 5 clients. Used by VendorRouter."""
    global _REGISTRY
    if _REGISTRY:
        return _REGISTRY
    for cls in (OpenAIClient, GeminiClient, GrokClient, DeepSeekClient, KimiClient):
        try:
            _REGISTRY[cls.vendor_name] = cls()
        except RuntimeError:
            # Missing API key — allow partial registry for dev/test
            pass
    return _REGISTRY
