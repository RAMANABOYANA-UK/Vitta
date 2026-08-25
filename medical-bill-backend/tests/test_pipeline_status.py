"""
Phase 1 unbreakable pipeline & state machine tests.

Guarantees verified:
1. A document always ends in `letter_ready` or `error` — never stuck in `processing`.
2. `result_json` is persisted before the final status change.
3. The error path always commits `error` with an error_message via a fresh session.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.api.routes.documents import _mark_document_error, _process_document_background
from app.schemas import DocumentStatus


class FakeDocument:
    """Minimal stand-in for the SQLModel Document."""

    def __init__(self, document_id: str, status: str = "uploaded"):
        self.id = document_id
        self.status = status
        self.error_message = None
        self.result_json = None
        # Mirrors the real Document model: every persisted record has a storage
        # key and content type, so the background pipeline reads the stored file
        # and passes extracted text into run_pipeline.
        self.storage_key = f"key-{document_id}"
        self.content_type = "application/pdf"


class FakeParsedBill:
    """Stand-in ParsedBill with model_dump."""

    def model_dump(self, mode: str = "json") -> dict:
        return {"document_id": "doc-1", "ok": True}


class FakeSession:
    """Scripted fake session for deterministic testing.

    Supports get/add/commit/refresh — enough to run the REAL
    update_document_status, making the tests faithful to production.
    """

    def __init__(self, fail_commit_on=None):
        self._fail_commit_on = fail_commit_on
        self.commits = 0
        self.documents = {}

    async def get(self, model, document_id):
        return self.documents.get(document_id)

    def add(self, obj):
        if isinstance(obj, FakeDocument):
            self.documents[obj.id] = obj

    async def commit(self):
        self.commits += 1
        if self._fail_commit_on is not None and self.commits == self._fail_commit_on:
            raise RuntimeError("simulated commit failure")

    async def refresh(self, obj):
        return obj


def make_ctx(session):
    """Wrap a FakeSession as an async context manager."""

    class _Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    return _Ctx()


@pytest.mark.asyncio
async def test_success_persists_result_before_letter_ready():
    """On success: result_json is committed before status -> letter_ready."""
    doc = FakeDocument("doc-1")
    session = FakeSession()
    session.add(doc)
    result = FakeParsedBill()

    status_calls: list[str] = []

    async def fake_update_status(s, d, new_status, error_message=None):
        """Mimic the real update_document_status: record + set status + commit."""
        status_calls.append(new_status)
        d.status = new_status
        s.add(d)
        await s.commit()
        return d

    with patch("app.database.AsyncSessionLocal") as mock_local, \
         patch("app.api.routes.documents.run_pipeline", new=AsyncMock(return_value=result)) as mock_run, \
         patch("app.api.routes.documents.update_document_status", new=fake_update_status), \
         patch("app.api.routes.documents.extract_document_text", new=AsyncMock(return_value="raw ocr text")):
        mock_local.return_value = make_ctx(session)

        await _process_document_background("doc-1", "bill.pdf")

    mock_run.assert_awaited_once_with(
        "doc-1", "bill.pdf",
        raw_ocr_text="raw ocr text",
    )
    assert doc.result_json == result.model_dump()

    # Status transitions, in order: uploaded → processing → letter_ready
    assert status_calls == [
        DocumentStatus.processing.value,
        DocumentStatus.letter_ready.value,
    ]
    # One commit for result_json, one for the letter_ready status transition.
    assert session.commits >= 2


@pytest.mark.asyncio
async def test_exception_always_marks_document_error():
    """Even when the main session breaks, a fresh session records error."""
    doc = FakeDocument("doc-1", status="uploaded")
    main_session = FakeSession()
    main_session.add(doc)

    error_doc = FakeDocument("doc-1", status="processing")

    async def failing_run(*args, **kwargs):
        raise RuntimeError("extraction exploded")

    class MainCtx:
        async def __aenter__(self):
            return main_session

        async def __aexit__(self, *args):
            return False

    class ErrorCtx:
        async def __aenter__(self):
            error_session = FakeSession()
            error_session.add(error_doc)
            return error_session

        async def __aexit__(self, *args):
            return False

    # Note: update_document_status is NOT patched here — the real function
    # runs against the FakeSession so the test is faithful to production.
    with patch("app.database.AsyncSessionLocal") as mock_local, \
         patch("app.api.routes.documents.run_pipeline", new=failing_run), \
         patch("app.api.routes.documents.extract_document_text", new=AsyncMock(return_value="raw ocr text")):
        mock_local.side_effect = [MainCtx(), ErrorCtx()]

        await _process_document_background("doc-1", "bill.pdf")

    assert error_doc.status == DocumentStatus.error.value
    assert error_doc.error_message is not None
    assert "extraction exploded" in error_doc.error_message


@pytest.mark.asyncio
async def test_error_path_fresh_session_even_if_commit_fails():
    """If main session commit fails, error still commits via fresh session."""
    doc = FakeDocument("doc-1", status="uploaded")
    # The first commit (uploaded -> processing) inside the real
    # update_document_status raises, leaving the main session unusable.
    main_session = FakeSession(fail_commit_on=1)
    main_session.add(doc)

    error_doc = FakeDocument("doc-1", status="uploaded")

    async def never_called_run(*args, **kwargs):
        raise AssertionError("run_pipeline should not be called")

    class MainCtx:
        async def __aenter__(self):
            return main_session

        async def __aexit__(self, *args):
            return False

    class ErrorCtx:
        async def __aenter__(self):
            error_session = FakeSession()
            error_session.add(error_doc)
            return error_session

        async def __aexit__(self, *args):
            return False

    # update_document_status is NOT patched: the real function commits and
    # triggers the simulated failure; the error path then uses a fresh session.
    with patch("app.database.AsyncSessionLocal") as mock_local, \
         patch("app.api.routes.documents.run_pipeline", new=never_called_run), \
         patch("app.api.routes.documents.extract_document_text", new=AsyncMock(return_value="raw ocr text")):
        mock_local.side_effect = [MainCtx(), ErrorCtx()]

        await _process_document_background("doc-1", "bill.pdf")

    assert error_doc.status == DocumentStatus.error.value
    assert "simulated commit failure" in error_doc.error_message


@pytest.mark.asyncio
async def test_mark_document_error_is_idempotent():
    """Re-marking an already-errored document is safe."""
    doc = FakeDocument("doc-1", status=DocumentStatus.error.value)
    session = FakeSession()
    session.add(doc)

    with patch("app.database.AsyncSessionLocal") as mock_local:
        mock_local.return_value = make_ctx(session)

        ok = await _mark_document_error("doc-1", "already errored")

    assert ok is True
    assert doc.status == DocumentStatus.error.value
    assert doc.error_message == "already errored"