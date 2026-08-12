"""Scoring service — adds pricing-anomaly and appeal-success fields to a
validated ParsedBill, with SHAP explanations.

This is the final stage of the pipeline. It consumes a validated ParsedBill
(verified flags set) and produces the pricing_anomaly and appeal_success blocks.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.ml.models import AppealSuccessModel, PricingAnomalyModel, get_models
from app.models import (
    AppealSuccess,
    ExtractionWarning,
    LineItem,
    ParsedBill,
    PricingAnomaly,
    ShapExplanation,
    WarningSeverity,
)

logger = logging.getLogger(__name__)


class ScoringService:
    """Scores a validated ParsedBill with the ML models."""

    def __init__(
        self,
        anomaly_model: Optional[PricingAnomalyModel] = None,
        appeal_model: Optional[AppealSuccessModel] = None,
    ):
        if anomaly_model is None or appeal_model is None:
            anomaly_model, appeal_model = get_models()
        self.anomaly_model = anomaly_model
        self.appeal_model = appeal_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def score(self, bill: ParsedBill) -> ParsedBill:
        """Add pricing-anomaly and appeal-success fields to the bill.

        Scores each line item, then aggregates to document-level scores.
        Returns a new ParsedBill with pricing_anomaly and appeal_success set.
        """
        result = bill.model_copy(deep=True)
        warnings: List[ExtractionWarning] = list(result.warnings)

        # Aggregate per-line scores
        line_anomaly_scores: List[float] = []
        line_appeal_scores: List[float] = []
        line_anomaly_explanations: List[ShapExplanation] = []
        line_appeal_explanations: List[ShapExplanation] = []

        for line in result.line_items:
            try:
                anomaly_prob, anomaly_score, is_anomalous, anomaly_expl = (
                    self._score_line_anomaly(line)
                )
                appeal_prob, appeal_score, recommendation, appeal_expl = (
                    self._score_line_appeal(line, is_anomalous)
                )

                line_anomaly_scores.append(anomaly_prob)
                line_appeal_scores.append(appeal_prob)
                line_anomaly_explanations.extend(
                    [ShapExplanation(**e) for e in anomaly_expl]
                )
                line_appeal_explanations.extend(
                    [ShapExplanation(**e) for e in appeal_expl]
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to score line %d: %s", line.line_number, exc
                )
                warnings.append(
                    ExtractionWarning(
                        code="SCORING_FAILED",
                        severity=WarningSeverity.MEDIUM,
                        message=f"Failed to score line {line.line_number}: {exc}",
                        field="pricing_anomaly",
                        line_number=line.line_number,
                    )
                )

        # Aggregate to document level
        if line_anomaly_scores:
            # Document anomaly = max of line anomalies (most egregious line drives it)
            doc_anomaly_prob = max(line_anomaly_scores)
            result.pricing_anomaly = PricingAnomaly(
                score=doc_anomaly_prob,
                calibrated_probability=doc_anomaly_prob,
                is_anomalous=doc_anomaly_prob >= settings.anomaly_threshold,
                threshold=settings.anomaly_threshold,
                explanation=line_anomaly_explanations[:10],  # cap for LLM
            )

        if line_appeal_scores:
            # Document appeal = max of line appeal probabilities
            doc_appeal_prob = max(line_appeal_scores)
            if doc_appeal_prob >= settings.appeal_threshold_strong:
                recommendation = "strong_appeal"
            elif doc_appeal_prob >= settings.appeal_threshold_moderate:
                recommendation = "moderate_appeal"
            elif doc_appeal_prob >= 0.3:
                recommendation = "weak_appeal"
            else:
                recommendation = "no_appeal"
            result.appeal_success = AppealSuccess(
                score=doc_appeal_prob,
                calibrated_probability=doc_appeal_prob,
                recommendation=recommendation,
                explanation=line_appeal_explanations[:10],
            )

        result.warnings = warnings
        return result

    # ------------------------------------------------------------------
    # Per-line scoring
    # ------------------------------------------------------------------
    def _score_line_anomaly(
        self, line: LineItem
    ) -> Tuple[float, float, bool, List[Dict]]:
        """Score a single line for pricing anomaly."""
        cpt = line.cpt_hcpcs_code
        geo = self._geography_for_line(line)
        prov = self._provider_type_for_line(line)
        payer = self._payer_for_line(line)
        units = line.units or 1.0
        charge = line.charge_amount or 0.0
        allowed = line.allowed_amount or 0.0

        prob, score, is_anomalous, expl = self.anomaly_model.explain_line(
            cpt_code=cpt,
            geography=geo,
            provider_type=prov,
            payer=payer,
            units=units,
            charge_amount=charge,
            allowed_amount=allowed,
        )
        return prob, score, is_anomalous, expl

    def _score_line_appeal(
        self, line: LineItem, is_anomalous: bool
    ) -> Tuple[float, float, str, List[Dict]]:
        """Score a single line for appeal success."""
        cpt = line.cpt_hcpcs_code
        geo = self._geography_for_line(line)
        prov = self._provider_type_for_line(line)
        payer = self._payer_for_line(line)
        units = line.units or 1.0
        charge = line.charge_amount or 0.0
        allowed = line.allowed_amount or 0.0

        prob, score, recommendation, expl = self.appeal_model.explain_line(
            cpt_code=cpt,
            geography=geo,
            provider_type=prov,
            payer=payer,
            units=units,
            charge_amount=charge,
            allowed_amount=allowed,
            is_anomalous=is_anomalous,
        )
        return prob, score, recommendation, expl

    # ------------------------------------------------------------------
    # Feature helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _geography_for_line(line: LineItem) -> str:
        """Best-effort geography. Defaults to 'NY' (a common default)."""
        # In a real deployment, geography would come from the provider's
        # location or the document metadata. For now, default.
        return "NY"

    @staticmethod
    def _provider_type_for_line(line: LineItem) -> str:
        """Map place of service to a provider type."""
        pos = line.place_of_service.value if line.place_of_service else "99"
        mapping = {
            "11": "primary_care",
            "12": "primary_care",
            "21": "hospital",
            "22": "outpatient_clinic",
            "23": "emergency",
            "24": "outpatient_clinic",
            "99": "primary_care",
        }
        return mapping.get(pos, "primary_care")

    @staticmethod
    def _payer_for_line(line: LineItem) -> str:
        return "payer_a"


def get_scoring_service() -> ScoringService:
    return ScoringService()