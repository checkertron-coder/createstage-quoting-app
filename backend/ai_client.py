"""
Unified AI client — routes to Claude (preferred) or Gemini (fallback).

Import this instead of gemini_client or claude_client directly.
Precedence: ANTHROPIC_API_KEY -> Claude, else GEMINI_API_KEY -> Gemini.

Provides the same interface as both claude_client and gemini_client:
  call_fast, call_deep, call_vision, is_configured, get_model_name, get_provider
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_provider = None  # cached after first call


def _get_provider():
    # type: () -> str
    global _provider
    if _provider is not None:
        return _provider

    from . import claude_client, gemini_client

    if claude_client.is_configured():
        _provider = "claude"
        logger.info("AI provider: Claude (ANTHROPIC_API_KEY configured)")
        return _provider
    elif gemini_client.is_configured():
        _provider = "gemini"
        logger.info("AI provider: Gemini (GEMINI_API_KEY configured, no ANTHROPIC_API_KEY)")
        return _provider
    else:
        _provider = "none"
        logger.warning("No AI provider configured (no ANTHROPIC_API_KEY or GEMINI_API_KEY)")
        return _provider


def is_configured():
    # type: () -> bool
    return _get_provider() != "none"


def get_provider():
    # type: () -> str
    return _get_provider()


def get_model_name(tier="deep"):
    # type: (str) -> str
    provider = _get_provider()
    if provider == "claude":
        from . import claude_client
        return claude_client.get_model_name(tier)
    elif provider == "gemini":
        from . import gemini_client
        return gemini_client.get_model_name(tier)
    return "none"


def call_fast(prompt, temperature=0.1, timeout=60, json_mode=True):
    # type: (str, float, int, bool) -> Optional[str]
    provider = _get_provider()
    if provider == "claude":
        from . import claude_client
        return claude_client.call_fast(prompt, temperature=temperature,
                                       timeout=timeout, json_mode=json_mode)
    elif provider == "gemini":
        from . import gemini_client
        return gemini_client.call_fast(prompt, temperature=temperature,
                                       timeout=timeout, json_mode=json_mode)
    return None


def call_deep(prompt, temperature=0.1, timeout=120, json_mode=True):
    # type: (str, float, int, bool) -> Optional[str]
    provider = _get_provider()
    if provider == "claude":
        from . import claude_client
        return claude_client.call_deep(prompt, temperature=temperature,
                                       timeout=timeout, json_mode=json_mode)
    elif provider == "gemini":
        from . import gemini_client
        return gemini_client.call_deep(prompt, temperature=temperature,
                                       timeout=timeout, json_mode=json_mode)
    return None


def call_vision(prompt, image_b64, mime_type, temperature=0.1, timeout=60,
                json_mode=True):
    # type: (str, str, str, float, int, bool) -> Optional[str]
    provider = _get_provider()
    if provider == "claude":
        from . import claude_client
        return claude_client.call_vision(prompt, image_b64, mime_type,
                                         temperature=temperature,
                                         timeout=timeout, json_mode=json_mode)
    elif provider == "gemini":
        from . import gemini_client
        return gemini_client.call_vision(prompt, image_b64, mime_type,
                                         temperature=temperature,
                                         timeout=timeout, json_mode=json_mode)
    return None


def reset_provider():
    # type: () -> None
    """Reset cached provider — useful for testing."""
    global _provider
    _provider = None
