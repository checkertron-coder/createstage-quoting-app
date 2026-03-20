"""
P59 — Login Hotfix: Show/Hide Password + Auth Debug.

Tests:
1. JWT access token lifetime is 60 minutes (not 15)
2. Login diagnostic logging: successful login logs email + SUCCESS
3. Login diagnostic logging: wrong password logs password_match=False
4. Login diagnostic logging: unverified user logs email_verified=False
5. Password toggle: auth.js contains togglePassword function
6. Password toggle: login form has password-wrapper class
7. Password toggle: register form has password-wrapper class
8. Password toggle: reset form has password-wrapper class
9. CSS has password-toggle styles
10. Login returns 403 with clear message for unverified users
"""

import logging
import os
import uuid
from datetime import datetime, timedelta

import pytest


# --- Helpers ---

def _register(client, email=None, password="testpass123"):
    """Register a user and return response data."""
    if email is None:
        email = "p59_%s@test.local" % uuid.uuid4().hex[:8]
    resp = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
    })
    assert resp.status_code == 200, resp.json()
    return resp.json()


def _make_unverified_user(client, db, email=None, password="testpass123"):
    """Register a user, then set email_verified=False to simulate unverified state.
    Also creates an email_verification token so login auto-verify doesn't kick in."""
    from backend import models
    data = _register(client, email=email, password=password)
    user = db.query(models.User).filter(models.User.id == data["user_id"]).first()
    user.email_verified = False
    token = models.EmailToken(
        user_id=user.id,
        token="fake_verify_%s" % uuid.uuid4().hex[:8],
        token_type="email_verification",
        expires_at=datetime.utcnow() + timedelta(hours=48),
    )
    db.add(token)
    db.commit()
    return data, user


# --- Tests ---

class TestJWTConfig:
    """JWT access token lifetime extended to 60 minutes."""

    def test_access_token_lifetime_is_60_minutes(self):
        """Config default is 60 minutes, not the old 15."""
        from backend.config import Settings
        s = Settings()
        assert s.JWT_ACCESS_EXPIRE_MINUTES == 60

    def test_access_token_expiry_in_token(self, client):
        """Access token issued on login should have ~60 min expiry."""
        from jose import jwt
        from backend.config import settings

        email = "p59_exp_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email, password="testpass123")
        resp = client.post("/api/auth/login", json={"email": email, "password": "testpass123"})
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        payload = jwt.decode(token, settings.JWT_SECRET or "dev-secret-key", algorithms=["HS256"])
        # exp should be ~60 min from now (allow 5 min tolerance)
        exp_dt = datetime.utcfromtimestamp(payload["exp"])
        delta = exp_dt - datetime.utcnow()
        assert delta.total_seconds() > 55 * 60, "Token expires too soon: %s" % delta
        assert delta.total_seconds() < 65 * 60, "Token expires too late: %s" % delta


class TestLoginDiagnosticLogging:
    """Login endpoint logs diagnostic info at each decision point."""

    def test_successful_login_logs_success(self, client, caplog):
        """Successful login should log [LOGIN] ... SUCCESS."""
        email = "p59_log_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email, password="testpass123")
        with caplog.at_level(logging.INFO, logger="backend.routers.auth"):
            resp = client.post("/api/auth/login", json={"email": email, "password": "testpass123"})
        assert resp.status_code == 200
        log_text = caplog.text
        assert "[LOGIN]" in log_text
        assert "SUCCESS" in log_text

    def test_wrong_password_logs_mismatch(self, client, caplog):
        """Wrong password should log password_match=False."""
        email = "p59_log2_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email, password="testpass123")
        with caplog.at_level(logging.INFO, logger="backend.routers.auth"):
            resp = client.post("/api/auth/login", json={"email": email, "password": "wrongpass"})
        assert resp.status_code == 401
        assert "password_match=False" in caplog.text

    def test_unverified_logs_email_verified_false(self, client, db, caplog):
        """Unverified user should log email_verified=False."""
        email = "p59_log3_%s@test.local" % uuid.uuid4().hex[:8]
        _make_unverified_user(client, db, email=email, password="testpass123")
        with caplog.at_level(logging.INFO, logger="backend.routers.auth"):
            resp = client.post("/api/auth/login", json={"email": email, "password": "testpass123"})
        assert resp.status_code == 403
        assert "email_verified=False" in caplog.text

    def test_nonexistent_user_logs_not_found(self, client, caplog):
        """Login with nonexistent email should log found=False."""
        with caplog.at_level(logging.INFO, logger="backend.routers.auth"):
            resp = client.post("/api/auth/login", json={
                "email": "nobody_%s@test.local" % uuid.uuid4().hex[:8],
                "password": "testpass123",
            })
        assert resp.status_code == 401
        assert "found=False" in caplog.text


class TestPasswordToggleFrontend:
    """Password toggle UI elements present in frontend files."""

    def test_auth_js_has_toggle_function(self):
        """auth.js should contain the togglePassword method."""
        with open("frontend/js/auth.js") as f:
            content = f.read()
        assert "togglePassword" in content

    def test_login_form_has_password_wrapper(self):
        """Login password field should be wrapped in .password-wrapper."""
        with open("frontend/js/auth.js") as f:
            content = f.read()
        # Check that login-password is inside a password-wrapper div
        assert 'id="login-password"' in content
        # The wrapper should appear near the login password field
        idx_wrapper = content.index('login-fields')
        idx_pw = content.index('login-password')
        section = content[idx_wrapper:idx_pw + 100]
        assert "password-wrapper" in section

    def test_register_form_has_password_wrapper(self):
        """Register password field should be wrapped in .password-wrapper."""
        with open("frontend/js/auth.js") as f:
            content = f.read()
        idx_wrapper = content.index('register-fields')
        idx_pw = content.index('reg-password')
        section = content[idx_wrapper:idx_pw + 100]
        assert "password-wrapper" in section

    def test_reset_form_has_password_wrapper(self):
        """Reset password field should be wrapped in .password-wrapper."""
        with open("frontend/js/auth.js") as f:
            content = f.read()
        idx_wrapper = content.index('reset-fields')
        idx_pw = content.index('reset-password"')
        section = content[idx_wrapper:idx_pw + 100]
        assert "password-wrapper" in section

    def test_css_has_password_toggle_styles(self):
        """CSS should have .password-toggle styling."""
        with open("frontend/css/style.css") as f:
            content = f.read()
        assert ".password-toggle" in content
        assert ".password-wrapper" in content


class TestLoginErrorMessages:
    """Login returns distinct status codes for different failures."""

    def test_unverified_returns_403_with_message(self, client, db):
        """Unverified user login returns 403 with descriptive message."""
        email = "p59_msg_%s@test.local" % uuid.uuid4().hex[:8]
        _make_unverified_user(client, db, email=email, password="testpass123")
        resp = client.post("/api/auth/login", json={"email": email, "password": "testpass123"})
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert "not verified" in detail.lower()

    def test_wrong_password_returns_401(self, client):
        """Wrong password returns 401, not 403."""
        email = "p59_msg2_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email, password="testpass123")
        resp = client.post("/api/auth/login", json={"email": email, "password": "wrongpass"})
        assert resp.status_code == 401
        assert "invalid" in resp.json()["detail"].lower()
