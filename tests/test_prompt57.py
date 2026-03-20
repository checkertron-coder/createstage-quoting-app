"""
P57 — Email Infrastructure: Password Reset + Email Verification.

Tests:
1. Registration auto-verifies when email service not configured
2. Email verification gate blocks unverified users on login
3. Admin email bypass on verification gate
4. Forgot password — always returns 200 (no email leak)
5. Forgot password — nonexistent email returns same response
6. Full password reset flow (request → use token → login)
7. Reset token consumed — second use fails
8. Expired token rejected
9. Verify email endpoint marks user as verified
10. Resend verification invalidates old tokens
11. Email service module: is_configured returns False without API key
12. EmailToken model fields
"""

import os
import uuid
from datetime import datetime, timedelta

import pytest


# --- Helpers ---

def _register(client, email=None, password="testpass123"):
    """Register a user and return response data."""
    if email is None:
        email = "p57_%s@test.local" % uuid.uuid4().hex[:8]
    resp = client.post("/api/auth/register", json={
        "email": email,
        "password": password,
    })
    assert resp.status_code == 200, resp.json()
    return resp.json()


def _make_unverified_user(client, db, email=None, password="testpass123"):
    """Register a user, then set email_verified=False to simulate unverified state.
    Also creates an email_verification token so the login auto-verify logic
    (which auto-verifies legacy users with no tokens) doesn't kick in."""
    from backend import models
    data = _register(client, email=email, password=password)
    user = db.query(models.User).filter(models.User.id == data["user_id"]).first()
    user.email_verified = False
    # Create a verification token to mark this as a "real" unverified user
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

class TestEmailVerificationGate:
    """Login gate: unverified users cannot log in."""

    def test_auto_verify_when_email_not_configured(self, client):
        """Without RESEND_API_KEY, registration auto-verifies the user."""
        data = _register(client)
        assert data["user"]["email_verified"] is True

    def test_unverified_user_blocked_on_login(self, client, db):
        """Unverified user gets 403 when logging in."""
        email = "unverified_%s@test.local" % uuid.uuid4().hex[:8]
        _data, _user = _make_unverified_user(client, db, email=email)

        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "testpass123",
        })
        assert resp.status_code == 403
        assert "not verified" in resp.json()["detail"].lower()

    def test_admin_email_bypasses_verification_gate(self, client, db):
        """APP_ADMIN_EMAIL user can log in without verification."""
        email = "admin_%s@test.local" % uuid.uuid4().hex[:8]
        _data, _user = _make_unverified_user(client, db, email=email)

        # Set the admin email env var
        old_val = os.environ.get("APP_ADMIN_EMAIL", "")
        os.environ["APP_ADMIN_EMAIL"] = email
        try:
            resp = client.post("/api/auth/login", json={
                "email": email,
                "password": "testpass123",
            })
            assert resp.status_code == 200
            assert "access_token" in resp.json()
        finally:
            os.environ["APP_ADMIN_EMAIL"] = old_val

    def test_verified_user_can_login(self, client):
        """Normal verified user logs in fine (auto-verified in test env)."""
        email = "verified_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email)

        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "testpass123",
        })
        assert resp.status_code == 200
        assert "access_token" in resp.json()


class TestForgotPassword:
    """POST /api/auth/forgot-password."""

    def test_forgot_password_existing_email(self, client):
        """Returns 200 for a registered email (no leak)."""
        email = "forgot_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email)

        resp = client.post("/api/auth/forgot-password", json={"email": email})
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    def test_forgot_password_nonexistent_email(self, client):
        """Returns same 200 for unknown email — no email enumeration."""
        resp = client.post("/api/auth/forgot-password", json={
            "email": "nobody_%s@nowhere.com" % uuid.uuid4().hex[:8],
        })
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()


class TestPasswordReset:
    """Full password reset flow using email tokens."""

    def test_full_reset_flow(self, client, db):
        """Register → request reset → use token → login with new password."""
        from backend import models

        email = "reset_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email, password="oldpassword1")

        # Request reset (creates token in DB)
        client.post("/api/auth/forgot-password", json={"email": email})

        # Find the token in DB
        user = db.query(models.User).filter(models.User.email == email).first()
        token_record = db.query(models.EmailToken).filter(
            models.EmailToken.user_id == user.id,
            models.EmailToken.token_type == "password_reset",
            models.EmailToken.is_used == False,
        ).first()
        assert token_record is not None

        # Reset password
        resp = client.post("/api/auth/reset-password", json={
            "token": token_record.token,
            "password": "newpassword1",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["user"]["email_verified"] is True

        # Login with new password
        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "newpassword1",
        })
        assert resp.status_code == 200

        # Old password no longer works
        resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "oldpassword1",
        })
        assert resp.status_code == 401

    def test_reset_token_consumed(self, client, db):
        """Token can only be used once."""
        from backend import models

        email = "consumed_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email)

        client.post("/api/auth/forgot-password", json={"email": email})

        user = db.query(models.User).filter(models.User.email == email).first()
        token_record = db.query(models.EmailToken).filter(
            models.EmailToken.user_id == user.id,
            models.EmailToken.token_type == "password_reset",
        ).first()

        # First use succeeds
        resp = client.post("/api/auth/reset-password", json={
            "token": token_record.token,
            "password": "newpasswd123",
        })
        assert resp.status_code == 200

        # Second use fails
        resp = client.post("/api/auth/reset-password", json={
            "token": token_record.token,
            "password": "another12345",
        })
        assert resp.status_code == 400
        assert "already been used" in resp.json()["detail"].lower()

    def test_expired_reset_token(self, client, db):
        """Expired token is rejected."""
        from backend import models

        email = "expired_%s@test.local" % uuid.uuid4().hex[:8]
        _register(client, email=email)

        client.post("/api/auth/forgot-password", json={"email": email})

        user = db.query(models.User).filter(models.User.email == email).first()
        token_record = db.query(models.EmailToken).filter(
            models.EmailToken.user_id == user.id,
            models.EmailToken.token_type == "password_reset",
        ).first()

        # Expire the token
        token_record.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()

        resp = client.post("/api/auth/reset-password", json={
            "token": token_record.token,
            "password": "newpasswd123",
        })
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    def test_reset_password_too_short(self, client):
        """Password under 8 chars is rejected."""
        resp = client.post("/api/auth/reset-password", json={
            "token": "fake-token",
            "password": "short",
        })
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]


class TestVerifyEmail:
    """GET /api/auth/verify-email?token=..."""

    def test_verify_email_success(self, client, db):
        """Valid verification token marks user as verified."""
        from backend import models

        email = "verify_%s@test.local" % uuid.uuid4().hex[:8]
        data, user = _make_unverified_user(client, db, email=email)

        # Create a verification token
        from backend.routers.auth import _create_email_token
        token = _create_email_token(user, "email_verification", db, expires_hours=48)

        # Verify
        resp = client.get("/api/auth/verify-email", params={"token": token})
        assert resp.status_code == 200
        assert "verified" in resp.json()["message"].lower()

        # User should now be verified
        db.refresh(user)
        assert user.email_verified is True

    def test_verify_email_invalid_token(self, client):
        """Invalid token returns 400."""
        resp = client.get("/api/auth/verify-email", params={"token": "bogus-token"})
        assert resp.status_code == 400

    def test_verify_email_already_used(self, client, db):
        """Used token returns 400."""
        from backend import models
        from backend.routers.auth import _create_email_token

        email = "used_%s@test.local" % uuid.uuid4().hex[:8]
        _data, user = _make_unverified_user(client, db, email=email)
        token = _create_email_token(user, "email_verification", db, expires_hours=48)

        # First use
        resp = client.get("/api/auth/verify-email", params={"token": token})
        assert resp.status_code == 200

        # Second use
        resp = client.get("/api/auth/verify-email", params={"token": token})
        assert resp.status_code == 400
        assert "already been used" in resp.json()["detail"].lower()


class TestResendVerification:
    """POST /api/auth/resend-verification."""

    def test_resend_invalidates_old_tokens(self, client, db):
        """Resending creates a new token and invalidates old ones."""
        from backend import models
        from backend.routers.auth import _create_email_token

        email = "resend_%s@test.local" % uuid.uuid4().hex[:8]
        _data, user = _make_unverified_user(client, db, email=email)

        # Create an initial verification token
        old_token = _create_email_token(user, "email_verification", db, expires_hours=48)

        # Resend
        resp = client.post("/api/auth/resend-verification", json={"email": email})
        assert resp.status_code == 200

        # Old token should be marked as used
        db.expire_all()
        old_record = db.query(models.EmailToken).filter(
            models.EmailToken.token == old_token,
        ).first()
        assert old_record.is_used is True

    def test_resend_unknown_email_no_leak(self, client):
        """Resend for unknown email returns same 200 response."""
        resp = client.post("/api/auth/resend-verification", json={
            "email": "nonexistent_%s@test.local" % uuid.uuid4().hex[:8],
        })
        assert resp.status_code == 200


class TestEmailServiceModule:
    """backend/email_service.py unit tests."""

    def test_is_configured_without_key(self):
        """Without RESEND_API_KEY, is_configured returns False."""
        from backend import email_service
        old = os.environ.pop("RESEND_API_KEY", None)
        try:
            assert email_service.is_configured() is False
        finally:
            if old is not None:
                os.environ["RESEND_API_KEY"] = old

    def test_send_verification_skips_without_key(self):
        """send_verification_email returns False when not configured."""
        from backend import email_service
        old = os.environ.pop("RESEND_API_KEY", None)
        try:
            result = email_service.send_verification_email("test@test.com", "fake-token")
            assert result is False
        finally:
            if old is not None:
                os.environ["RESEND_API_KEY"] = old

    def test_send_reset_skips_without_key(self):
        """send_password_reset_email returns False when not configured."""
        from backend import email_service
        old = os.environ.pop("RESEND_API_KEY", None)
        try:
            result = email_service.send_password_reset_email("test@test.com", "fake-token")
            assert result is False
        finally:
            if old is not None:
                os.environ["RESEND_API_KEY"] = old


class TestEmailTokenModel:
    """EmailToken ORM model."""

    def test_create_email_token(self, db):
        """EmailToken can be created and queried."""
        from backend import models

        # Create a user first
        user = models.User(
            email="tokentest_%s@test.local" % uuid.uuid4().hex[:8],
            password_hash="fakehash",
        )
        db.add(user)
        db.commit()

        token = models.EmailToken(
            user_id=user.id,
            token="test-token-abc123",
            token_type="email_verification",
            expires_at=datetime.utcnow() + timedelta(hours=48),
        )
        db.add(token)
        db.commit()

        # Query
        found = db.query(models.EmailToken).filter(
            models.EmailToken.token == "test-token-abc123"
        ).first()
        assert found is not None
        assert found.token_type == "email_verification"
        assert found.is_used is False
        assert found.user_id == user.id
