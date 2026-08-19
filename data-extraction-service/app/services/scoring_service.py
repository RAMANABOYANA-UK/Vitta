"""Scoring service — adds pricing-anomaly and appeal-success fields to a
validated ParsedBill, with SHAP explanations.

This is the final stage of the pipeline. It consumes a validated ParsedBill
(verified flags set) and produces the pricing_anomaly and appeal_success
extension fields, plus maps the results into the Vitta contract's
`appeal_prediction` and `denial_codes` fields so the backend and Rust engine
can consume them directly.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from app.config import settings
from app.ml.models import AppealSuccessModel, PricingAnomalyModel, get_models
from app.models import (
    AppealPrediction,
    AppealSuccess,
    ExtractionWarning,
    Flag,
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
        Returns a new ParsedBill with pricing_anomaly, appeal_success,
        appeal_prediction, and denial_codes set.
        """
        result = bill.model_copy(deep=True)
        warnings: List[ExtractionWarning] = list(result.warnings)

        # Aggregate per-line scores
        line_anomaly_scores: List[float] = []
        line_appeal_scores: List[float] = []
        line_anomaly_explanations: List[ShapExplanation] = []
        line_appeal_explanations: List[ShapExplanation] = []
        denial_codes: List[Dict] = []

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

                # If anomalous, raise a flag on the line item (Vitta contract)
                if is_anomalous:
                    severity = "warning" if anomaly_prob < 0.85 else "critical"
                    line.flags.append(
                        Flag(
                            type="pricing_anomaly",
                            severity=severity,
                            message=(
                                f"Charge of ${line.charge_amount:,.2f} is "
                                f"anomalous relative to regional benchmarks "
                                f"(calibrated probability {anomaly_prob:.0%})."
                            ),
                            rule_id="RULE-PRICE-001",
                            shap_contribution=round(anomaly_prob, 4),
                        )
                    )
                    # Add a denial code entry (normalized to include "code" key)
                    denial_codes.append(
                        {
                            "code": "CO-50",
                            "reason": "Charge exceeds regional fair-price benchmarks.",
                            "severity": "warning",
                            "amount": round(line.charge_amount, 2),
                            "line_item_id": line.id,
                            "line_item_description": line.description,
                            "cpt_hcpcs": line.cpt_hcpcs,
                        }
                    )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to score line %s: %s", line.id, exc
                )
                warnings.append(
                    ExtractionWarning(
                        code="SCORING_FAILED",
                        severity=WarningSeverity.MEDIUM,
                        message=f"Failed to score line {line.id}: {exc}",
                        field="pricing_anomaly",
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

            # Map into the Vitta contract's appeal_prediction field
            result.appeal_prediction = AppealPrediction(
                success_probability=round(doc_appeal_prob, 2),
                confidence_interval=[
                    round(max(0.0, doc_appeal_prob - 0.05), 2),
                    round(min(1.0, doc_appeal_prob + 0.05), 2),
                ],
                top_factors=[
                    e.human_readable for e in line_appeal_explanations[:5]
                ],
                recommendation=recommendation,
                explanation=line_appeal_explanations[:10],
            )

        # Set denial codes on the bill (Vitta contract)
        if denial_codes:
            result.denial_codes = denial_codes

        result.warnings = warnings
        return result

    # ------------------------------------------------------------------
    # Per-line scoring
    # ------------------------------------------------------------------
    def _score_line_anomaly(
        self, line: LineItem
    ) -> Tuple[float, float, bool, List[Dict]]:
        """Score a single line for pricing anomaly."""
        cpt = line.cpt_hcpcs or "99213"
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
        cpt = line.cpt_hcpcs or "99213"
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
        # The Vitta LineItem doesn't carry place_of_service; default to primary_care.
        return "primary_care"

    @staticmethod
    def _payer_for_line(line: LineItem) -> str:
        return "payer_a"


def get_scoring_service() -> ScoringService:
    return ScoringService()