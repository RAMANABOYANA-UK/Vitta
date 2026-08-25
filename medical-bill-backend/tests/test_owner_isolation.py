"""DB-level test proving per-document owner isolation (no cross-user PHI access).

The crypto helpers are covered in test_security_auth.py; this file exercises the
REAL ownership gate (_get_document_or_404) against a real in-memory async DB:
owner A can read their own document, and owner B — even a logged-in user — gets
404 (never 403, to avoid confirming the document exists).
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
from app.api.routes.documents import _get_document_or_404


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield Session
    await engine.dispose()


def _user(email: str) -> models.User:
    return models.User(email=email, password_hash="x", email_verified=True)


def _doc(owner_id: str) -> models.Document:
    return models.Document(
        owner_id=owner_id,
        original_filename="bill.pdf",
        storage_key="k/bill.pdf",
        content_type="application/pdf",
    )


@pytest.mark.asyncio
async def test_owner_can_read_own_document(db):
    async with db() as session:
        alice = _user("alice@example.com")
        session.add(alice)
        await session.commit()
        await session.refresh(alice)

        doc = _doc(alice.id)
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        found = await _get_document_or_404(doc.id, session, alice)
        assert found.id == doc.id


@pytest.mark.asyncio
async def test_other_user_cannot_read_owners_document(db):
    """A different authenticated user must get a 404 (not the document, not 403)."""
    async with db() as session:
        alice = _user("alice@example.com")
        bob = _user("bob@example.com")
        session.add_all([alice, bob])
        await session.commit()
        await session.refresh(alice)
        await session.refresh(bob)

        doc = _doc(alice.id)
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        with pytest.raises(HTTPException) as ei:
            await _get_document_or_404(doc.id, session, bob)
        assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_orphaned_document_denied_to_everyone(db):
    """A document with no owner (legacy) is fail-closed: no user can read it."""
    async with db() as session:
        bob = _user("bob@example.com")
        session.add(bob)
        await session.commit()
        await session.refresh(bob)

        orphan = _doc(owner_id=None)  # owner_id None
        session.add(orphan)
        await session.commit()
        await session.refresh(orphan)

        with pytest.raises(HTTPException) as ei:
            await _get_document_or_404(orphan.id, session, bob)
        assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_nonexistent_document_returns_404(db):
    async with db() as session:
        bob = _user("bob@example.com")
        session.add(bob)
        await session.commit()
        await session.refresh(bob)
        with pytest.raises(HTTPException) as ei:
            await _get_document_or_404("does-not-exist", session, bob)
        assert ei.value.status_code == 404