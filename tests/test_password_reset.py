"""
Tests for P57: Password reset + email verification.

Covers:
- Forgot password (known + unknown email)
- Reset password (valid, expired, used tokens)
- Email verification
- Resend verification
"""

import hashlib
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
    """Register a user and return (email, password, user_id)."""
    email = "reset-test@fabricator.com"
    password = "strongpassword123"
    with patch("backend.routers.auth.email_service") as mock_email:
        mock_email.send_email_verification.return_value = False
        resp = client.post("/api/auth/register", json={
            "email": email,
            "password": password,
        })
    assert resp.status_code == 200
    user_id = resp.json()["user_id"]
    return email, password, user_id


# --- Forgot Password ---

class TestForgotPassword:
    def test_known_email_returns_200(self, client, registered_user):
        email, _, _ = registered_user
        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.send_password_reset.return_value = True
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
            mock_email.send_password_reset.return_value = True
            client.post("/api/auth/forgot-password", json={"email": email})

        token = db.query(models.PasswordResetToken).filter(
            models.PasswordResetToken.user_id == user_id,
            models.PasswordResetToken.token_type == "reset",
        ).first()
        assert token is not None
        assert token.used_at is None
        assert token.expires_at > datetime.utcnow()

    def test_calls_email_service(self, client, registered_user):
        email, _, _ = registered_user
        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.send_password_reset.return_value = True
            client.post("/api/auth/forgot-password", json={"email": email})
        mock_email.send_password_reset.assert_called_once()
        call_args = mock_email.send_password_reset.call_args
        assert call_args[0][0] == email
        assert "token=" in call_args[0][1]  # reset URL contains token


# --- Reset Password ---

class TestResetPassword:
    def _create_reset_token(self, db, user_id, hours=1):
        """Helper: create a reset token and return the raw token."""
        import secrets
        raw_token = secrets.token_urlsafe(32)
        record = models.PasswordResetToken(
            user_id=user_id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            token_type="reset",
            expires_at=datetime.utcnow() + timedelta(hours=hours),
        )
        db.add(record)
        db.commit()
        return raw_token

    def test_valid_token_resets_password(self, client, db, registered_user):
        email, _, user_id = registered_user
        raw_token = self._create_reset_token(db, user_id)

        resp = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "new_password": "newpassword456",
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
            "new_password": "newpassword456",
        })
        assert resp1.status_code == 200

        # Second use fails
        resp2 = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "new_password": "anotherpassword789",
        })
        assert resp2.status_code == 400

    def test_expired_token_fails(self, client, db, registered_user):
        _, _, user_id = registered_user
        # Create token that expired 1 hour ago
        raw_token = self._create_reset_token(db, user_id, hours=-1)

        resp = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "new_password": "newpassword456",
        })
        assert resp.status_code == 400
        assert "expired" in resp.json()["detail"].lower()

    def test_invalid_token_fails(self, client):
        resp = client.post("/api/auth/reset-password", json={
            "token": "totally-bogus-token",
            "new_password": "newpassword456",
        })
        assert resp.status_code == 400

    def test_short_password_rejected(self, client, db, registered_user):
        _, _, user_id = registered_user
        raw_token = self._create_reset_token(db, user_id)

        resp = client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "new_password": "short",
        })
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]

    def test_old_password_stops_working(self, client, db, registered_user):
        email, old_password, user_id = registered_user
        raw_token = self._create_reset_token(db, user_id)

        client.post("/api/auth/reset-password", json={
            "token": raw_token,
            "new_password": "newpassword456",
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
        import secrets
        raw_token = secrets.token_urlsafe(32)
        record = models.PasswordResetToken(
            user_id=user_id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            token_type="verify",
            expires_at=datetime.utcnow() + timedelta(hours=hours),
        )
        db.add(record)
        db.commit()
        return raw_token

    def test_verify_sets_is_verified(self, client, db, registered_user):
        email, _, user_id = registered_user

        # User starts unverified
        user = db.query(models.User).filter(models.User.id == user_id).first()
        assert user.is_verified is False

        raw_token = self._create_verify_token(db, user_id)
        resp = client.get("/api/auth/verify-email?token=%s" % raw_token)
        assert resp.status_code == 200
        assert resp.json()["email"] == email

        # Refresh from DB
        db.refresh(user)
        assert user.is_verified is True

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

        # Get auth token
        login_resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "strongpassword123",
        })
        headers = {"Authorization": "Bearer %s" % login_resp.json()["access_token"]}

        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.send_email_verification.return_value = True
            resp = client.post("/api/auth/resend-verification", headers=headers)
        assert resp.status_code == 200
        assert "sent" in resp.json()["message"].lower()

    def test_resend_for_verified_user(self, client, db, registered_user):
        email, _, user_id = registered_user

        # Mark as verified
        user = db.query(models.User).filter(models.User.id == user_id).first()
        user.is_verified = True
        db.commit()

        login_resp = client.post("/api/auth/login", json={
            "email": email,
            "password": "strongpassword123",
        })
        headers = {"Authorization": "Bearer %s" % login_resp.json()["access_token"]}

        resp = client.post("/api/auth/resend-verification", headers=headers)
        assert resp.status_code == 200
        assert "already verified" in resp.json()["message"].lower()

    def test_resend_requires_auth(self, client):
        resp = client.post("/api/auth/resend-verification")
        assert resp.status_code in (401, 403)


# --- Registration triggers verification email ---

class TestRegistrationVerification:
    def test_registration_calls_send_verification(self, client):
        with patch("backend.routers.auth.email_service") as mock_email:
            mock_email.send_email_verification.return_value = True
            resp = client.post("/api/auth/register", json={
                "email": "newuser@fabricator.com",
                "password": "strongpassword123",
            })
        assert resp.status_code == 200
        # _send_verification_email calls _create_token_record then email_service.send_email_verification
        mock_email.send_email_verification.assert_called_once()

    def test_new_user_starts_unverified(self, client, db):
        with patch("backend.routers.auth.email_service"):
            resp = client.post("/api/auth/register", json={
                "email": "unverified@fabricator.com",
                "password": "strongpassword123",
            })
        assert resp.status_code == 200
        user = resp.json()["user"]
        assert user["is_verified"] is False
