"""Shared rate limiter — imported by main.py and individual routers."""

import os
from slowapi import Limiter
from slowapi.util import get_remote_address


def _get_user_or_ip(request):
    """Extract user ID from JWT Authorization header, fall back to IP.

    Used for per-user rate limiting on authenticated endpoints.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from .auth import decode_token
            token = auth_header.split(" ", 1)[1]
            payload = decode_token(token)
            return "user:%s" % payload.get("sub", get_remote_address(request))
        except Exception:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=get_remote_address)

# Disable rate limiting in test environment
if os.environ.get("TESTING") == "1":
    limiter.enabled = False
