"""Unit tests for the FastAPI endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    DocumentMetadata,
    DocumentType,
    FieldConfidence,
    LineItem,
    ParsedBill,
    TotalsBlock,
)

client = TestClient(app)


def _make_draft_bill() -> ParsedBill:
    """A valid draft bill for testing /validate and /score."""
    conf = FieldConfidence(
        ocr_confidence=0.95,
        extraction_confidence=0.9,
        verified=False,
    )
    line = LineItem(
        line_number=1,
        cpt_hcpcs_code="99214",
        charge_amount=200.0,
        allowed_amount=170.0,
        paid_amount=136.0,
        patient_responsibility=34.0,
        code_confidence=conf,
        amount_confidence=conf,
    )
    totals = TotalsBlock(
        billed_total=200.0,
        adjustments_total=30.0,
        paid_total=136.0,
        patient_responsibility_total=34.0,
    )
    return ParsedBill(
        document_id="api-test-doc",
        metadata=DocumentMetadata(document_type=DocumentType.BILL),
        line_items=[line],
        totals=totals,
    )


class TestHealth:
    def test_health(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "llm_configured" in data
        assert "database_connected" in data


class TestExtractEndpoint:
    def test_extract_bill(self):
        resp = client.post(
            "/extract",
            json={
                "raw_ocr_text": (
                    "Provider: City Medical Group\n"
                    "NPI: 1234567890\n"
                    "99214 Office visit $200.00\n"
                    "Total Billed: $200.00\n"
                ),
                "document_id": "api-extract-test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "api-extract-test"
        assert data["metadata"]["document_type"] == "bill"
        assert len(data["line_items"]) == 1
        assert data["line_items"][0]["cpt_hcpcs_code"] == "99214"

    def test_extract_empty_text_400(self):
        resp = client.post("/extract", json={"raw_ocr_text": "   "})
        assert resp.status_code == 400


class TestValidateEndpoint:
    def test_validate_valid_bill(self):
        bill = _make_draft_bill()
        resp = client.post("/validate", json={"parsed_bill": bill.model_dump(mode="json")})
        assert resp.status_code == 200
        data = resp.json()
        # Valid code should be verified
        assert data["line_items"][0]["code_confidence"]["verified"] is True
        # Reconciled amounts should be verified
        assert data["line_items"][0]["amount_confidence"]["verified"] is True
        # Totals should reconcile
        assert data["totals"]["reconciliation"]["matches_patient_responsibility"] is True

    def test_validate_invalid_code_flagged(self):
        bill = _make_draft_bill()
        bill.line_items[0].cpt_hcpcs_code = "99999"
        resp = client.post("/validate", json={"parsed_bill": bill.model_dump(mode="json")})
        assert resp.status_code == 200
        data = resp.json()
        assert data["line_items"][0]["code_confidence"]["verified"] is False
        assert data["line_items"][0]["code_validation"]["status"] == "ambiguous"
        assert any(w["code"] == "VERIFICATION_FAILED" for w in data["warnings"])


class TestScoreEndpoint:
    def test_score_valid_bill(self):
        bill = _make_draft_bill()
        resp = client.post("/score", json={"parsed_bill": bill.model_dump(mode="json")})
        assert resp.status_code == 200
        data = resp.json()
        assert "pricing_anomaly" in data
        assert "appeal_success" in data
        assert data["pricing_anomaly"]["calibrated_probability"] is not None
        assert data["appeal_success"]["calibrated_probability"] is not None
        # SHAP explanations present
        assert len(data["pricing_anomaly"]["explanation"]) > 0
        assert len(data["appeal_success"]["explanation"]) > 0
        # Human-readable explanations
        for e in data["pricing_anomaly"]["explanation"]:
            assert "human_readable" in e
            assert isinstance(e["human_readable"], str)


class TestPipelineEndpoint:
    def test_full_pipeline(self):
        resp = client.post(
            "/pipeline",
            json={
                "raw_ocr_text": (
                    "Provider: City Medical Group\n"
                    "NPI: 1234567890\n"
                    "99214 Office visit $200.00\n"
                    "Total Billed: $200.00\n"
                ),
                "document_id": "api-pipeline-test",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "api-pipeline-test"
        assert len(data["line_items"]) == 1
        assert "pricing_anomaly" in data
        assert "appeal_success" in data