"""Vendor adapter layer — client ABC, 5 concrete clients, router."""
from .client import (
    VendorClient,
    VendorResponse,
    CANONICAL_GEN_CONFIG,
    VendorError,
    RateLimitError,
    ContentFilterError,
    TransientServerError,
    AuthError,
    TimeoutError_,
)
from .clients import (
    OpenAIClient,
    GeminiClient,
    GrokClient,
    DeepSeekClient,
    KimiClient,
    register_default_clients,
)
from .router import VendorRouter, MultiVendorResult, prompt_hash, BudgetExceededError

__all__ = [
    "VendorClient",
    "VendorResponse",
    "CANONICAL_GEN_CONFIG",
    "VendorError",
    "RateLimitError",
    "ContentFilterError",
    "TransientServerError",
    "AuthError",
    "TimeoutError_",
    "OpenAIClient",
    "GeminiClient",
    "GrokClient",
    "DeepSeekClient",
    "KimiClient",
    "register_default_clients",
    "VendorRouter",
    "MultiVendorResult",
    "prompt_hash",
    "BudgetExceededError",
]
