"""End-to-end tests for the Auth/PHI gate completion: email verification
(issue -> redeem -> login gate), resend, logout-everywhere, and logout.

These exercise the real FastAPI route functions against a real in-memory async
session (no HTTP/TestClient), covering the actual SQL + security logic. Mail
delivery is stubbed by capturing the one-time token the route "sends".
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app import models  # noqa: F401  (registers tables)
from app.api.routes import auth as auth_routes


@pytest_asyncio.fixture
async def db():
    """An isolated in-memory async engine + session factory with tables."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield Session
    await engine.dispose()


PASSWORD = "verystrongpass1"


async def _register(db, monkeypatch, email="patient@example.com"):
    """Register a user, capturing the emailed verification token if any."""
    captured: dict = {}
    monkeypatch.setattr(auth_routes, "send_verification_email", _capture(captured))
    async with db() as session:
        user = await auth_routes.register(
            auth_routes.UserCreate(email=email, password=PASSWORD), session
        )
    return user, captured


def _capture(store: dict):
    def _send(to_email: str, token: str):
        store["token"] = token

    return _send


@pytest.mark.asyncio
async def test_default_register_is_immediately_usable(db, monkeypatch):
    """Verification disabled (default): registration marks the user verified, no
    email is sent, and existing dev/demo flows are unchanged."""
    user, captured = await _register(db, monkeypatch)
    assert not captured  # no verification email
    async with db() as session:
        u = await session.get(models.User, user.user.id)
        assert u.email_verified is True


@pytest.mark.asyncio
async def test_verification_gates_login_and_token_redeems(db, monkeypatch):
    """With EMAIL_VERIFICATION_REQUIRED=True: register leaves the user unverified
    and mails a token; login is refused with 403 email_not_verified until the
    token is redeemed; login succeeds afterwards."""
    monkeypatch.setattr(auth_routes.settings, "EMAIL_VERIFICATION_REQUIRED", True)
    user, captured = await _register(db, monkeypatch)
    assert captured, "a verification email should be sent when required"
    token = captured["token"]

    async with db() as session:
        # Unverified: correct password still refused.
        with pytest.raises(HTTPException) as ei:
            await auth_routes.login(
                auth_routes.LoginRequest(email=user.user.email, password=PASSWORD), session
            )
        assert ei.value.status_code == 403
        assert ei.value.detail == "email_not_verified"

        # Redeem the token -> verified.
        resp = await auth_routes.verify_email(
            auth_routes.EmailVerificationRequest(token=token), session
        )
        assert resp.email_verified is True

        # Login now succeeds.
        tok = await auth_routes.login(
            auth_routes.LoginRequest(email=user.user.email, password=PASSWORD), session
        )
        assert tok.access_token


@pytest.mark.asyncio
async def test_resend_verification_reissues_token(db, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "EMAIL_VERIFICATION_REQUIRED", True)
    user, captured = await _register(db, monkeypatch)

    new_captured: dict = {}
    monkeypatch.setattr(auth_routes, "send_verification_email", _capture(new_captured))

    async with db() as session:
        u = await session.get(models.User, user.user.id)
        await auth_routes.resend_verification(u, session)
        assert new_captured.get("token")

        # Old token is now invalid (single active verification token).
        with pytest.raises(HTTPException) as ei:
            await auth_routes.verify_email(
                auth_routes.EmailVerificationRequest(token=captured["token"]), session
            )
        assert ei.value.status_code == 400


@pytest.mark.asyncio
async def test_logout_everywhere_revokes_all_sessions(db, monkeypatch):
    user, _ = await _register(db, monkeypatch)
    async with db() as session:
        u = await session.get(models.User, user.user.id)
        tok1, _ = await auth_routes._issue_session(session, u)
        tok2, _ = await auth_routes._issue_session(session, u)

        await auth_routes.logout_everywhere(u, session)

        for tok in (tok1, tok2):
            with pytest.raises(HTTPException):
                await auth_routes.get_current_user(
                    authorization=f"Bearer {tok}", session=session
                )


@pytest.mark.asyncio
async def test_logout_revokes_presented_session_only(db, monkeypatch):
    import sqlmodel

    user, _ = await _register(db, monkeypatch)
    async with db() as session:
        u = await session.get(models.User, user.user.id)
        tok1, _ = await auth_routes._issue_session(session, u)
        tok2, _ = await auth_routes._issue_session(session, u)

        await auth_routes.logout(authorization=f"Bearer {tok1}", session=session)

        res = await session.exec(
            sqlmodel.select(models.UserSession).where(
                models.UserSession.token_hash == auth_routes.hash_token(tok1)
            )
        )
        assert res.first() is None
        res2 = await session.exec(
            sqlmodel.select(models.UserSession).where(
                models.UserSession.token_hash == auth_routes.hash_token(tok2)
            )
        )
        assert res2.first() is not None
@pytest.mark.asyncio
async def test_verification_token_is_single_use(db, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "EMAIL_VERIFICATION_REQUIRED", True)
    _, captured = await _register(db, monkeypatch)
    async with db() as session:
        await auth_routes.verify_email(
            auth_routes.EmailVerificationRequest(token=captured["token"]), session
        )
        with pytest.raises(HTTPException) as ei:
            await auth_routes.verify_email(
                auth_routes.EmailVerificationRequest(token=captured["token"]), session
            )
        assert ei.value.status_code == 400
