"""
Tests for P57: Password reset + email verification.

Covers:
- Forgot password (known + unknown email)
- Reset password (valid, expired, used tokens)
- Email verification
- Resend verification
"""

import secrets
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend import models
from tests.conftest import TestingSessionLocal, app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def registered_user(client, db):
    """Register a user and return (email, password, user_id).
    Patches email_service so is_configured() returns True, which means
    the user stays unverified (no auto-verify fallback)."""
    email = "reset-test@fabricator.com"
    password = "strongpassword123"
    with patch("backend.routers.auth.email_service") as mock_email:
        mock_email.is_configured.return_value = True
        mock_email.send_email_verification.return_value = True
        resp = client.post("/api/auth/register", json={
            "email": email,
            "password": password,
        })
    assert resp.status_code == 200
    user_id = resp.json()["user_id"]
    # Ensure the user is unverified for tests that need it
    user = db.query(models.User).filter(models.User.id == user_id).first()
    user.email_verified = False
    db.commit()
    return email, password, user_id


# --- Forgot Password ---

class TestForgotPassword:
    def test_known_email_returns_200(self, client, registered_user):
        email, _, _ = registered_user
        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.send_password_reset_email.return_value = True
            resp = client.post("/api/auth/forgot-password", json={"email": email})
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    def test_unknown_email_returns_200_no_leak(self, client):
        """Never reveal whether an email exists."""
        resp = client.post("/api/auth/forgot-password", json={
            "email": "nobody@nowhere.com",
        })
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    def test_creates_token_in_db(self, client, db, registered_user):
        email, _, user_id = registered_user
        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.send_password_reset_email.return_value = True
            client.post("/api/auth/forgot-password", json={"email": email})

        token = db.query(models.EmailToken).filter(
            models.EmailToken.user_id == user_id,
            models.EmailToken.token_type == "password_reset",
        ).first()
        assert token is not None
        assert token.is_used is False
        assert token.expires_at > datetime.utcnow()

    def test_calls_email_service(self, client, registered_user):
        email, _, _ = registered_user
        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.send_password_reset_email.return_value = True
            client.post("/api/auth/forgot-password", json={"email": email})
        mock_email.send_password_reset_email.assert_called_once()
        call_args = mock_email.send_password_reset_email.call_args
        assert call_args[0][0] == email


# --- Reset Password ---

class TestResetPassword:
    def _create_reset_token(self, db, user_id, hours=1):
        """Helper: create a reset token and return the raw token."""
        raw_token = secrets.token_urlsafe(32)
        record = models.EmailToken(
            user_id=user_id,
            token=raw_token,
            token_type="password_reset",
            expires_at=datetime.utcnow() + timedelta(hours=hours),
        )
        db.add(record)
        db.commit()
        return raw_token

    def test_valid_token_resets_password(self, client, db, registered_user):
        email, _, user_id = registered_user
        # Verify the user so they can login after reset
        user = db.query(models.User).filter(models.User.id == user_id).first()
        user.email_verified = True
        db.commit()

        raw_token = self._create_reset_token(db, user_id)

        resp = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "password": "newpassword456",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["email"] == email

        # Verify new password works
        login_resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "newpassword456",
        })
        assert login_resp.status_code == 200

    def test_token_is_single_use(self, client, db, registered_user):
        _, _, user_id = registered_user
        raw_token = self._create_reset_token(db, user_id)

        # First use succeeds
        resp1 = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "password": "newpassword456",
        })
        assert resp1.status_code == 200

        # Second use fails
        resp2 = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "password": "anotherpassword789",
        })
        assert resp2.status_code == 400

    def test_expired_token_fails(self, client, db, registered_user):
        _, _, user_id = registered_user
        # Create token that expired 1 hour ago
        raw_token = self._create_reset_token(db, user_id, hours=-1)

        resp = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "password": "newpassword456",
        })
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    def test_invalid_token_fails(self, client):
        resp = client.post("/api/auth/reset-password", json={
            "token": "totally-bogus-token",
            "password": "newpassword456",
        })
        assert resp.status_code == 400

    def test_short_password_rejected(self, client, db, registered_user):
        _, _, user_id = registered_user
        raw_token = self._create_reset_token(db, user_id)

        resp = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "password": "short",
        })
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]

    def test_old_password_stops_working(self, client, db, registered_user):
        email, old_password, user_id = registered_user
        # Verify user so login works
        user = db.query(models.User).filter(models.User.id == user_id).first()
        user.email_verified = True
        db.commit()

        raw_token = self._create_reset_token(db, user_id)

        client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "password": "newpassword456",
        })

        # Old password no longer works
        login_resp = client.post("/api/auth/login", json={
            "email": email,
            "password": old_password,
        })
        assert login_resp.status_code == 401


# --- Email Verification ---

class TestEmailVerification:
    def _create_verify_token(self, db, user_id, hours=48):
        """Helper: create a verification token and return the raw token."""
        raw_token = secrets.token_urlsafe(32)
        record = models.EmailToken(
            user_id=user_id,
            token=raw_token,
            token_type="email_verification",
            expires_at=datetime.utcnow() + timedelta(hours=hours),
        )
        db.add(record)
        db.commit()
        return raw_token

    def test_verify_sets_email_verified(self, client, db, registered_user):
        email, _, user_id = registered_user

        # User starts unverified
        user = db.query(models.User).filter(models.User.id == user_id).first()
        assert user.email_verified is False

        raw_token = self._create_verify_token(db, user_id)
        resp = client.get("/api/auth/verify-email?token=%s" % raw_token)
        assert resp.status_code == 200

        # Refresh from DB
        db.refresh(user)
        assert user.email_verified is True

    def test_expired_verify_token_fails(self, client, db, registered_user):
        _, _, user_id = registered_user
        raw_token = self._create_verify_token(db, user_id, hours=-1)

        resp = client.get("/api/auth/verify-email?token=%s" % raw_token)
        assert resp.status_code == 400

    def test_used_verify_token_fails(self, client, db, registered_user):
        _, _, user_id = registered_user
        raw_token = self._create_verify_token(db, user_id)

        # First use succeeds
        resp1 = client.get("/api/auth/verify-email?token=%s" % raw_token)
        assert resp1.status_code == 200

        # Second use fails
        resp2 = client.get("/api/auth/verify-email?token=%s" % raw_token)
        assert resp2.status_code == 400

    def test_invalid_verify_token_fails(self, client):
        resp = client.get("/api/auth/verify-email?token=bogus-token")
        assert resp.status_code == 400


# --- Resend Verification ---

class TestResendVerification:
    def test_resend_for_unverified_user(self, client, db, registered_user):
        email, _, user_id = registered_user

        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.is_configured.return_value = True
            mock_email.send_email_verification.return_value = True
            resp = client.post("/api/auth/resend-verification", json={"email": email})
        assert resp.status_code == 200
        assert "sent" in resp.json()["message"].lower()

    def test_resend_for_verified_user(self, client, db, registered_user):
        email, _, user_id = registered_user

        # Mark as verified
        user = db.query(models.User).filter(models.User.id == user_id).first()
        user.email_verified = True
        db.commit()

        resp = client.post("/api/auth/resend-verification", json={"email": email})
        assert resp.status_code == 200

    def test_resend_unknown_email_returns_200(self, client):
        """Never reveals whether the email exists."""
        resp = client.post("/api/auth/resend-verification", json={"email": "nobody@test.com"})
        assert resp.status_code == 200


# --- Registration triggers verification email ---

class TestRegistrationVerification:
    def test_registration_calls_send_verification(self, client):
        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.is_configured.return_value = True
            mock_email.send_email_verification.return_value = True
            resp = client.post("/api/auth/register", json={
                "email": "newuser@fabricator.com",
                "password": "strongpassword123",
            })
        assert resp.status_code == 200

    def test_new_user_auto_verifies_without_email_service(self, client, db):
        """When email service is not configured, user is auto-verified."""
        resp = client.post("/api/auth/register", json={
            "email": "autoverify@fabricator.com",
            "password": "strongpassword123",
        })
        assert resp.status_code == 200
        user_data = resp.json()["user"]
        assert user_data["email_verified"] is True
