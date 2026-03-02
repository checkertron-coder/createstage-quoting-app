"""
Tests for the centralized Gemini client module.
20 tests covering model resolution, API calls, error handling, and helpers.
"""

import json
import socket
import urllib.error
from io import BytesIO
from unittest.mock import patch, MagicMock

import pytest

from backend.gemini_client import (
    _resolve_model,
    get_model_name,
    is_configured,
    call_fast,
    call_deep,
    call_vision,
    _call_gemini,
)


def _mock_response(text="hello"):
    """Build a mock urlopen response returning Gemini-shaped JSON."""
    body = json.dumps({
        "candidates": [{"content": {"parts": [{"text": text}]}}]
    }).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# --- Model resolution tests ---

class TestModelResolution:
    def test_resolve_fast_model_primary(self):
        """GEMINI_FAST_MODEL takes priority for fast tier."""
        with patch.dict("os.environ", {
            "GEMINI_FAST_MODEL": "fast-model",
            "GEMINI_CUTLIST_MODEL": "cutlist-model",
        }):
            assert _resolve_model("fast") == "fast-model"

    def test_resolve_fast_model_fallback_cutlist(self):
        """Falls back to GEMINI_CUTLIST_MODEL when GEMINI_FAST_MODEL unset."""
        env = {"GEMINI_CUTLIST_MODEL": "cutlist-model"}
        with patch.dict("os.environ", env, clear=False):
            # Make sure GEMINI_FAST_MODEL is not set
            with patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("GEMINI_FAST_MODEL", None)
                assert _resolve_model("fast") == "cutlist-model"

    def test_resolve_fast_model_default(self):
        """Falls back to gemini-2.5-flash when no fast env vars set."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GEMINI_FAST_MODEL", None)
            os.environ.pop("GEMINI_CUTLIST_MODEL", None)
            assert _resolve_model("fast") == "gemini-2.5-flash"

    def test_resolve_deep_model_primary(self):
        """GEMINI_DEEP_MODEL takes priority for deep tier."""
        with patch.dict("os.environ", {
            "GEMINI_DEEP_MODEL": "deep-model",
            "GEMINI_MODEL": "general-model",
        }):
            assert _resolve_model("deep") == "deep-model"

    def test_resolve_deep_model_fallback_model(self):
        """Falls back to GEMINI_MODEL when GEMINI_DEEP_MODEL unset."""
        with patch.dict("os.environ", {"GEMINI_MODEL": "general-model"}, clear=False):
            import os
            os.environ.pop("GEMINI_DEEP_MODEL", None)
            assert _resolve_model("deep") == "general-model"

    def test_resolve_deep_model_default(self):
        """Falls back to gemini-2.5-flash when no deep env vars set."""
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GEMINI_DEEP_MODEL", None)
            os.environ.pop("GEMINI_MODEL", None)
            assert _resolve_model("deep") == "gemini-2.5-flash"


# --- No API key tests ---

class TestNoApiKey:
    def test_call_fast_no_api_key(self):
        """call_fast returns None when no API key."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            assert call_fast("test prompt") is None

    def test_call_deep_no_api_key(self):
        """call_deep returns None when no API key."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            assert call_deep("test prompt") is None

    def test_call_vision_no_api_key(self):
        """call_vision returns None when no API key."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            assert call_vision("test", "base64data", "image/jpeg") is None


# --- Successful call tests ---

class TestSuccessfulCalls:
    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_call_fast_success(self, mock_urlopen):
        """call_fast returns text on successful response."""
        mock_urlopen.return_value = _mock_response('{"result": "ok"}')
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = call_fast("test prompt")
            assert result == '{"result": "ok"}'

    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_call_deep_success(self, mock_urlopen):
        """call_deep returns text on successful response."""
        mock_urlopen.return_value = _mock_response("deep result")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = call_deep("test prompt")
            assert result == "deep result"

    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_call_vision_success(self, mock_urlopen):
        """call_vision passes image data in payload."""
        mock_urlopen.return_value = _mock_response("vision result")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = call_vision("describe", "abc123", "image/png")
            assert result == "vision result"
            # Verify the payload includes inline_data
            call_args = mock_urlopen.call_args
            req = call_args[0][0]
            payload = json.loads(req.data)
            parts = payload["contents"][0]["parts"]
            assert len(parts) == 2
            assert parts[1]["inline_data"]["mime_type"] == "image/png"
            assert parts[1]["inline_data"]["data"] == "abc123"


# --- Error handling tests ---

class TestErrorHandling:
    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_404_deprecated_model(self, mock_urlopen):
        """404 response returns None (model deprecated)."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 404, "Not Found", {}, BytesIO(b""))
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = call_fast("test")
            assert result is None

    @patch("backend.gemini_client.time.sleep")
    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_429_retries_once(self, mock_urlopen, mock_sleep):
        """429 triggers one retry after 2s sleep, then succeeds."""
        mock_urlopen.side_effect = [
            urllib.error.HTTPError("url", 429, "Rate Limited", {}, BytesIO(b"")),
            _mock_response("retry success"),
        ]
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = call_fast("test")
            assert result == "retry success"
            mock_sleep.assert_called_once_with(2)

    @patch("backend.gemini_client.time.sleep")
    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_429_twice_returns_none(self, mock_urlopen, mock_sleep):
        """Double 429 returns None."""
        mock_urlopen.side_effect = [
            urllib.error.HTTPError("url", 429, "Rate Limited", {}, BytesIO(b"")),
            urllib.error.HTTPError("url", 429, "Rate Limited", {}, BytesIO(b"")),
        ]
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = call_fast("test")
            assert result is None

    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_general_exception_returns_none(self, mock_urlopen):
        """ConnectionError returns None."""
        mock_urlopen.side_effect = ConnectionError("network down")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = call_deep("test")
            assert result is None

    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_timeout_returns_none(self, mock_urlopen):
        """socket.timeout returns None."""
        mock_urlopen.side_effect = socket.timeout("timed out")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = call_deep("test")
            assert result is None


# --- Helper tests ---

class TestHelpers:
    def test_is_configured_true(self):
        """is_configured returns True when key is set."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "real-key"}):
            assert is_configured() is True

    def test_is_configured_false(self):
        """is_configured returns False when key is empty."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            assert is_configured() is False

    def test_get_model_name(self):
        """get_model_name returns the resolved model string."""
        with patch.dict("os.environ", {"GEMINI_MODEL": "my-model"}, clear=False):
            import os
            os.environ.pop("GEMINI_DEEP_MODEL", None)
            assert get_model_name("deep") == "my-model"

    @patch("backend.gemini_client.urllib.request.urlopen")
    def test_custom_timeout_passed(self, mock_urlopen):
        """Custom timeout is forwarded to urlopen."""
        mock_urlopen.return_value = _mock_response("ok")
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            call_deep("test", timeout=45)
            call_args = mock_urlopen.call_args
            assert call_args[1].get("timeout") == 45 or call_args[0][1] == 45
