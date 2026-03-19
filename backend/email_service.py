"""
Email service — all outbound email goes through this module.

Uses Resend (resend.com) as the email provider.
If RESEND_API_KEY is not set, logs a warning and skips sending.
"""

import logging
import os

logger = logging.getLogger(__name__)


def is_configured():
    # type: () -> bool
    """Check whether email sending is available."""
    return bool(os.getenv("RESEND_API_KEY", "").strip())


def _get_from():
    # type: () -> str
    return os.getenv("RESEND_FROM", "CreateQuote <onboarding@resend.dev>")


def _get_app_url():
    # type: () -> str
    return os.getenv("APP_URL", "http://localhost:8000").rstrip("/")


def send_verification_email(to_email, token):
    # type: (str, str) -> bool
    """Send email verification link after registration."""
    if not is_configured():
        logger.warning("RESEND_API_KEY not set — skipping verification email to %s", to_email)
        return False

    app_url = _get_app_url()
    verify_url = "%s/app?action=verify-email&token=%s" % (app_url, token)

    html = (
        "<div style='font-family: -apple-system, BlinkMacSystemFont, sans-serif; "
        "max-width: 480px; margin: 0 auto; padding: 40px 20px;'>"
        "<h2 style='color: #1a202c; margin-bottom: 8px;'>Verify your email</h2>"
        "<p style='color: #4a5568; font-size: 15px; line-height: 1.6;'>"
        "Welcome to CreateQuote. Click the button below to verify your email "
        "address and activate your account.</p>"
        "<a href='%s' style='display: inline-block; background: #2d3748; "
        "color: #fff; padding: 12px 28px; border-radius: 6px; "
        "text-decoration: none; font-weight: 600; margin: 20px 0;'>"
        "Verify Email</a>"
        "<p style='color: #718096; font-size: 13px;'>This link expires in 48 hours.</p>"
        "<p style='color: #a0aec0; font-size: 12px; margin-top: 30px;'>"
        "If you didn't create an account, ignore this email.</p>"
        "</div>"
    ) % verify_url

    return _send(to_email, "Verify your CreateQuote email", html)


def send_password_reset_email(to_email, token):
    # type: (str, str) -> bool
    """Send password reset link."""
    if not is_configured():
        logger.warning("RESEND_API_KEY not set — skipping reset email to %s", to_email)
        return False

    app_url = _get_app_url()
    reset_url = "%s/app?action=reset-password&token=%s" % (app_url, token)

    html = (
        "<div style='font-family: -apple-system, BlinkMacSystemFont, sans-serif; "
        "max-width: 480px; margin: 0 auto; padding: 40px 20px;'>"
        "<h2 style='color: #1a202c; margin-bottom: 8px;'>Reset your password</h2>"
        "<p style='color: #4a5568; font-size: 15px; line-height: 1.6;'>"
        "We received a request to reset your CreateQuote password. "
        "Click the button below to choose a new one.</p>"
        "<a href='%s' style='display: inline-block; background: #2d3748; "
        "color: #fff; padding: 12px 28px; border-radius: 6px; "
        "text-decoration: none; font-weight: 600; margin: 20px 0;'>"
        "Reset Password</a>"
        "<p style='color: #718096; font-size: 13px;'>This link expires in 1 hour "
        "and can only be used once.</p>"
        "<p style='color: #a0aec0; font-size: 12px; margin-top: 30px;'>"
        "If you didn't request this, ignore this email. Your password won't change.</p>"
        "</div>"
    ) % reset_url

    return _send(to_email, "Reset your CreateQuote password", html)


def _send(to_email, subject, html):
    # type: (str, str, str) -> bool
    """Send an email via Resend. Returns True on success."""
    api_key = os.getenv("RESEND_API_KEY", "").strip()
    if not api_key:
        return False

    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            "from": _get_from(),
            "to": [to_email],
            "subject": subject,
            "html": html,
        })
        logger.info("Email sent to %s: %s", to_email, subject)
        return True
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False
