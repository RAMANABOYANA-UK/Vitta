"""A minimal email-notification boundary for the auth flows.

There is no SMTP/transactional provider wired into this repository, so the
sender is deliberately dependency-light and honest: in development it logs the
verification link (which is how a developer exercises the flow locally);
``EMAIL_EMAIL_SENDER=...``/SMTP wiring is left as the production integration
point. The important contract for the auth routes is only that a
``verification_url`` can be produced and "sent" without raising — so tests can
assert the token route end-to-end without an email server.
"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


def build_verification_url(token: str) -> str:
    """Return the absolute URL an end user clicks to verify their email.

    The frontend's verify flow reads ``?token=...`` from the URL, so the href
    follows the login page's revert-to-dir convention.
    """
    base = settings.VERIFICATION_BASE_URL.rstrip("/") if getattr(settings, "VERIFICATION_BASE_URL", None) else ""
    qt = f"?token={token}"
    if base:
        return f"{base}{qt}"
    return f"/verify-email{qt}"


def send_verification_email(email: str, token: str) -> None:
    """Deliver (or, in dev/absent-provider, log) the verification email.

    Real PHI deployments MUST replace this with a transactional sender; logging
    a one-time verification link is acceptable for a local/dev flow only.
    """
    url = build_verification_url(token)
    logger.info(
        "email.verification queued | to=%s | url=%s (dev-delivery: no SMTP provider wired)",
        email,
        url,
    )


def send_appeal_letter_email(email: str, subject: str, letter_markdown: str) -> None:
    """Deliver (or, in dev/absent-provider, log) an appeal letter.

    Mirrors the verification sender: real PHI deployments swap this for a
    transactional provider. The letter is never logged (it is PHI); only the
    recipient and subject are.
    """
    logger.info(
        "email.appeal_letter queued | to=%s | subject=%.120s | body_chars=%d "
        "(dev-delivery: no SMTP provider wired)",
        email,
        subject,
        len(letter_markdown or ""),
    )