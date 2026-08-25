"""Unit tests for the stdlib auth crypto helpers (app.core.security).

These are pure standard-library (PBKDF2 / SHA-256 / hmac) and require no app
config, DB, or third-party packages, so they run anywhere.
"""

from __future__ import annotations

from app.core.security import (
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_round_trip():
    enc = hash_password("correct horse battery staple", iterations=50_000)
    assert enc.startswith("pbkdf2_sha256$50000$")
    assert verify_password("correct horse battery staple", enc) is True


def test_wrong_password_rejected():
    enc = hash_password("s3cret-value", iterations=50_000)
    assert verify_password("s3cret-valuE", enc) is False
    assert verify_password("", enc) is False
    assert verify_password("totally different", enc) is False


def test_same_password_hashes_differ_by_salt():
    a = hash_password("same-input", iterations=50_000)
    b = hash_password("same-input", iterations=50_000)
    assert a != b  # random per-password salt
    assert verify_password("same-input", a)
    assert verify_password("same-input", b)


def test_verify_password_never_raises_on_garbage():
    for bad in ["", "not-encoded", "a$b$c", "md5$1$x$y", "pbkdf2_sha256$notint$x$y"]:
        assert verify_password("whatever", bad) is False


def test_empty_password_rejected_on_hash():
    try:
        hash_password("")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("hash_password('') should raise ValueError")


def test_session_token_is_random_and_urlsafe():
    t1 = generate_session_token()
    t2 = generate_session_token()
    assert t1 != t2
    assert len(t1) >= 32
    # url-safe alphabet only
    assert all(c.isalnum() or c in "-_" for c in t1)


def test_token_hash_is_deterministic_and_hidden():
    tok = generate_session_token()
    assert hash_token(tok) == hash_token(tok)          # deterministic → lookupable
    assert hash_token(tok) != hash_token(tok + "x")    # collision-resistant
    assert tok not in hash_token(tok)                  # raw token not recoverable
    assert len(hash_token(tok)) == 64                  # sha256 hex
