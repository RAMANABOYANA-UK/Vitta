"""Unit tests for P5 #31 — appeal letter download/email plumbing.

Covers the PHI-safe mailer boundary and the email-request schema. The gateway
routes themselves are thin over these (owner-scoped, audited), and are covered
by import-level validation in the rest of the backend suite.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import LetterEmailRequest
from app.services.mailer import send_appeal_letter_email


def test_appeal_letter_email_sends_without_raising(caplog):
    """The mailer boundary accepts a letter without raising and never logs the body."""
    with caplog.at_level("INFO"):
        send_appeal_letter_email(
            email="patient@example.com",
            subject="Your appeal for claim GX-1",
            letter_markdown="Re: Claim GX-1 ... private PHI content ...",
        )
    combined = caplog.text
    assert "appeal_letter" in combined
    # The PHI body must never be logged.
    assert "private PHI content" not in combined


def test_letter_email_request_normalizes_and_validates_email():
    req = LetterEmailRequest(email="  PATIENT@Example.COM ")
    assert req.email == "patient@example.com"
    with pytest.raises(ValidationError):
        LetterEmailRequest(email="not-an-email")


def test_letter_email_request_default_subject_is_optional():
    req = LetterEmailRequest(email="a@b.com")
    assert req.subject is None