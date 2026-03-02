"""
Centralized Gemini API client.

All Gemini calls across the app go through this module. Provides tiered
model selection (fast vs deep), unified error handling, retry on 429,
and structured logging.

Model resolution (backward-compatible with existing env vars):
  FAST:  GEMINI_FAST_MODEL -> GEMINI_CUTLIST_MODEL -> "gemini-2.5-flash"
  DEEP:  GEMINI_DEEP_MODEL -> GEMINI_MODEL -> "gemini-2.5-flash"
"""

import json
import logging
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash"


def _resolve_model(tier):
    # type: (str) -> str
    """Resolve model name from env vars with fallback chain."""
    if tier == "fast":
        return (
            os.getenv("GEMINI_FAST_MODEL")
            or os.getenv("GEMINI_CUTLIST_MODEL")
            or _DEFAULT_MODEL
        )
    # deep (default)
    return (
        os.getenv("GEMINI_DEEP_MODEL")
        or os.getenv("GEMINI_MODEL")
        or _DEFAULT_MODEL
    )


def get_model_name(tier="deep"):
    # type: (str) -> str
    """Return the resolved model name for a tier."""
    return _resolve_model(tier)


def is_configured():
    # type: () -> bool
    """Check whether a Gemini API key is available."""
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


def call_fast(prompt, temperature=0.1, timeout=15, json_mode=True):
    # type: (str, float, int, bool) -> Optional[str]
    """Call Gemini with the fast model. Returns response text or None."""
    return _call_gemini(prompt, tier="fast", temperature=temperature,
                        timeout=timeout, json_mode=json_mode)


def call_deep(prompt, temperature=0.2, timeout=120, json_mode=True):
    # type: (str, float, int, bool) -> Optional[str]
    """Call Gemini with the deep model. Returns response text or None."""
    return _call_gemini(prompt, tier="deep", temperature=temperature,
                        timeout=timeout, json_mode=json_mode)


def call_vision(prompt, image_b64, mime_type, temperature=0.1, timeout=30, json_mode=True):
    # type: (str, str, str, float, int, bool) -> Optional[str]
    """Call Gemini Vision with an image. Returns response text or None."""
    return _call_gemini(prompt, tier="fast", temperature=temperature,
                        timeout=timeout, json_mode=json_mode,
                        image_b64=image_b64, image_mime=mime_type)


def _call_gemini(prompt, tier="deep", temperature=0.2, timeout=120,
                 json_mode=True, image_b64=None, image_mime=None):
    # type: (str, str, float, int, bool, Optional[str], Optional[str]) -> Optional[str]
    """Internal: execute a Gemini API call with retry on 429."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.debug("No GEMINI_API_KEY — skipping Gemini call")
        return None

    model = _resolve_model(tier)
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "%s:generateContent?key=%s" % (model, api_key)
    )

    # Build payload
    parts = [{"text": prompt}]
    if image_b64 and image_mime:
        parts.append({"inline_data": {"mime_type": image_mime, "data": image_b64}})

    gen_config = {"temperature": temperature}
    if json_mode:
        gen_config["responseMimeType"] = "application/json"

    payload = json.dumps({
        "contents": [{"parts": parts}],
        "generationConfig": gen_config,
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    start = time.time()
    retried = False

    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                result = json.loads(response.read())
                text = result["candidates"][0]["content"]["parts"][0]["text"]
                elapsed = time.time() - start
                logger.info("gemini %s [%s] %.1fs", tier, model, elapsed)
                return text
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.warning("Gemini model deprecated: %s (404)", model)
                return None
            if e.code == 429 and not retried:
                retried = True
                logger.info("Gemini 429 — retrying in 2s (%s)", model)
                time.sleep(2)
                continue
            if e.code == 429:
                logger.warning("Gemini double 429 — giving up (%s)", model)
                return None
            logger.warning("Gemini HTTP %d: %s", e.code, e.reason)
            return None
        except socket.timeout:
            elapsed = time.time() - start
            logger.warning("Gemini timeout after %.1fs (%s)", elapsed, model)
            return None
        except Exception as e:
            logger.warning("Gemini call failed: %s", e)
            return None

    return None
