"""
Centralized AI client for the CreateStage quoting app. All AI generation
calls use this module. Provides: call_fast, call_deep, call_vision,
is_configured, get_model_name.

Model resolution:
  FAST:  CLAUDE_FAST_MODEL -> "claude-opus-4-6"
  DEEP:  CLAUDE_DEEP_MODEL -> "claude-opus-4-6"

Set ANTHROPIC_API_KEY in environment to enable.
"""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_FAST = "claude-opus-4-6"
_DEFAULT_DEEP = "claude-opus-4-6"

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


def _resolve_model(tier):
    # type: (str) -> str
    if tier == "fast":
        return os.getenv("CLAUDE_FAST_MODEL", _DEFAULT_FAST)
    return os.getenv("CLAUDE_DEEP_MODEL", _DEFAULT_DEEP)


def get_model_name(tier="deep"):
    # type: (str) -> str
    """Return the resolved model name for a tier."""
    return _resolve_model(tier)


def is_configured():
    # type: () -> bool
    """Check whether an Anthropic API key is available."""
    return bool(os.getenv("ANTHROPIC_API_KEY", "").strip())


def call_fast(prompt, temperature=0.1, timeout=60, json_mode=True):
    # type: (str, float, int, bool) -> Optional[str]
    """Call Claude with the fast model. Returns response text or None."""
    return _call_claude(prompt, tier="fast", temperature=temperature,
                        timeout=timeout, json_mode=json_mode)


def call_deep(prompt, temperature=0.1, timeout=120, json_mode=True):
    # type: (str, float, int, bool) -> Optional[str]
    """Call Claude with the deep model. Returns response text or None."""
    return _call_claude(prompt, tier="deep", temperature=temperature,
                        timeout=timeout, json_mode=json_mode)


def call_vision(prompt, image_b64, mime_type, temperature=0.1, timeout=60,
                json_mode=True):
    # type: (str, str, str, float, int, bool) -> Optional[str]
    """Call Claude Vision with an image. Returns response text or None."""
    print(f"[VISION-DEBUG] call_vision ENTERED: b64_len={len(image_b64) if image_b64 else 0}, "
          f"mime={mime_type}, prompt_len={len(prompt) if prompt else 0}", flush=True)
    # Validate inputs before sending
    if not image_b64:
        logger.error("call_vision: image_b64 is empty/None")
        return None
    if not mime_type:
        logger.error("call_vision: mime_type is empty/None")
        return None

    b64_len = len(image_b64) if image_b64 else 0
    logger.info("call_vision: image_b64 length=%d, mime_type=%s, prompt_len=%d",
                b64_len, mime_type, len(prompt) if prompt else 0)

    # Anthropic API limit: ~20MB base64 per image
    if b64_len > 20 * 1024 * 1024:
        logger.error("call_vision: image too large (%d bytes base64, max ~20MB)", b64_len)
        return None

    return _call_claude(prompt, tier="fast", temperature=temperature,
                        timeout=timeout, json_mode=json_mode,
                        image_b64=image_b64, image_mime=mime_type)


def _call_claude(prompt, tier="deep", temperature=0.1, timeout=120,
                 json_mode=True, image_b64=None, image_mime=None):
    # type: (str, str, float, int, bool, Optional[str], Optional[str]) -> Optional[str]
    """Execute a Claude API call via httpx."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        logger.debug("No ANTHROPIC_API_KEY — skipping Claude call")
        return None

    model = _resolve_model(tier)

    # Build message content
    content = []
    if image_b64 and image_mime:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_mime,
                "data": image_b64,
            }
        })
    content.append({"type": "text", "text": prompt})

    # System prompt for JSON mode
    system = None
    if json_mode:
        system = (
            "You are a fabrication engineering AI. Respond ONLY with valid JSON. "
            "No markdown, no code blocks, no explanation — just the JSON object or array."
        )

    payload = {
        "model": model,
        "max_tokens": 16384,
        "temperature": temperature,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        payload["system"] = system

    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    is_vision = bool(image_b64)
    start = time.time()

    try:
        import httpx
        with httpx.Client(timeout=timeout) as client:
            if is_vision:
                # Log payload size (not content) for vision debugging
                payload_size = len(json.dumps(payload))
                logger.info("claude vision request: model=%s payload_size=%d bytes",
                            model, payload_size)
            response = client.post(ANTHROPIC_API_URL, headers=headers,
                                   json=payload)
            if response.status_code != 200:
                # Capture the FULL error response body before raise_for_status
                elapsed = time.time() - start
                logger.error(
                    "Claude API error %d (%s%s) after %.1fs: %s",
                    response.status_code,
                    tier,
                    "+vision" if is_vision else "",
                    elapsed,
                    response.text[:2000],
                )
                return None
            result = response.json()
            text = result["content"][0]["text"]
            elapsed = time.time() - start
            logger.info("claude %s%s [%s] %.1fs tokens_in=%d tokens_out=%d",
                        tier, "+vision" if is_vision else "", model, elapsed,
                        result.get("usage", {}).get("input_tokens", 0),
                        result.get("usage", {}).get("output_tokens", 0))
            return text

    except Exception as e:
        elapsed = time.time() - start
        err_name = type(e).__name__
        logger.error("Claude call failed (%s%s, %s) after %.1fs: %s",
                     tier, "+vision" if is_vision else "",
                     err_name, elapsed, e)
        return None
