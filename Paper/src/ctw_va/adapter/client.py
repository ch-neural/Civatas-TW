"""VendorClient ABC + CANONICAL_GEN_CONFIG (spec §B1)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
import os


CANONICAL_GEN_CONFIG: dict = {
    "temperature": 0.0,
    "top_p": 1.0,
    "max_tokens": 512,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
}


@dataclass
class VendorResponse:
    vendor: str
    model_id: str
    status: str  # 'ok' | 'refusal_text' | 'refusal_filter' | 'error'
    raw_text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    finish_reason: str = ""
    system_fingerprint: Optional[str] = None
    error_detail: Optional[str] = None
    attempt: int = 1


class VendorError(Exception):
    """Base — raised when a retry-eligible error occurs."""


class RateLimitError(VendorError):
    pass


class ContentFilterError(VendorError):
    """Vendor refused via content filter (different from text-based refusal)."""


class TransientServerError(VendorError):
    pass


class AuthError(VendorError):
    pass


class TimeoutError_(VendorError):  # avoid clash with builtin
    pass


class VendorClient(ABC):
    vendor_name: str = ""  # subclass overrides
    model_id: str = ""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get(self._env_key())
        if not self.api_key:
            raise RuntimeError(
                f"{self.vendor_name}: API key not set. Put {self._env_key()} in .env."
            )

    @abstractmethod
    def _env_key(self) -> str:
        """Environment variable name holding the API key (e.g. 'OPENAI_API_KEY')."""

    @abstractmethod
    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        seed: int,
    ) -> VendorResponse:
        """Run a single chat completion with canonical config + vendor-specific tweaks."""


def call_with_retry_sync(fn, attempts: int = 4, base_delay: float = 1.0):
    """Retry helper — exponential backoff + jitter."""
    import random
    import time
    last_exc = None
    for i in range(attempts):
        try:
            return fn(), i + 1
        except (RateLimitError, TransientServerError, TimeoutError_) as e:
            last_exc = e
            if i == attempts - 1:
                raise
            delay = base_delay * (2 ** i) + random.random() * 0.5
            time.sleep(delay)
        except (AuthError, ContentFilterError):
            raise
    raise last_exc
