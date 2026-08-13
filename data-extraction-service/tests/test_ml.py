"""Unit tests for the ML models — training, calibration, and SHAP explainability."""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.models import (
    AppealSuccessModel,
    PricingAnomalyModel,
    train_all_models,
)
from app.ml.synthetic_data import SyntheticDataGenerator


@pytest.fixture(scope="module")
def trained_models():
    """Train both models on a small synthetic dataset (fast for tests)."""
    gen = SyntheticDataGenerator(seed=42, n_samples=2000)
    df = gen.generate()

    anomaly = PricingAnomalyModel()
    anomaly.train(df)

    appeal = AppealSuccessModel()
    appeal.train(df)

    return anomaly, appeal


class TestPricingAnomalyModel:
    def test_trains_and_outputs_calibrated_probability(self, trained_models):
        anomaly, _ = trained_models
        assert anomaly.trained is True
        assert "roc_auc" in anomaly.metrics
        assert anomaly.metrics["roc_auc"] > 0.7  # should learn the pattern

    def test_explain_line_returns_structured_output(self, trained_models):
        anomaly, _ = trained_models
        prob, score, is_anomalous, expl = anomaly.explain_line(
            cpt_code="99214",
            geography="NY",
            provider_type="primary_care",
            payer="payer_a",
            units=1.0,
            charge_amount=500.0,  # high charge → likely anomalous
            allowed_amount=170.0,
        )
        assert 0.0 <= prob <= 1.0
        assert 0.0 <= score <= 1.0
        assert isinstance(is_anomalous, bool)
        assert isinstance(expl, list)
        # SHAP explanations should be human-readable key-value pairs
        for e in expl:
            assert "feature" in e
            assert "contribution" in e
            assert "direction" in e
            assert "human_readable" in e
            assert isinstance(e["human_readable"], str)
            assert len(e["human_readable"]) > 0

    def test_normal_charge_low_anomaly(self, trained_models):
        anomaly, _ = trained_models
        prob, _, is_anomalous, _ = anomaly.explain_line(
            cpt_code="99214",
            geography="NY",
            provider_type="primary_care",
            payer="payer_a",
            units=1.0,
            charge_amount=170.0,  # fair price
            allowed_amount=170.0,
        )
        assert prob < 0.5  # normal charge should not be anomalous


class TestAppealSuccessModel:
    def test_trains_and_outputs_calibrated_probability(self, trained_models):
        _, appeal = trained_models
        assert appeal.trained is True
        assert "roc_auc" in appeal.metrics
        assert appeal.metrics["roc_auc"] > 0.6

    def test_explain_line_returns_recommendation(self, trained_models):
        _, appeal = trained_models
        prob, score, recommendation, expl = appeal.explain_line(
            cpt_code="99214",
            geography="NY",
            provider_type="primary_care",
            payer="payer_a",
            units=1.0,
            charge_amount=500.0,
            allowed_amount=170.0,
            is_anomalous=True,
        )
        assert 0.0 <= prob <= 1.0
        assert recommendation in (
            "strong_appeal",
            "moderate_appeal",
            "weak_appeal",
            "no_appeal",
        )
        assert isinstance(expl, list)
        for e in expl:
            assert "human_readable" in e
            assert isinstance(e["human_readable"], str)

    def test_anomalous_charge_higher_appeal_probability(self, trained_models):
        _, appeal = trained_models
        # Anomalous charge should have higher appeal probability than normal
        prob_anomalous, _, _, _ = appeal.explain_line(
            cpt_code="99214",
            geography="NY",
            provider_type="primary_care",
            payer="payer_a",
            units=1.0,
            charge_amount=800.0,
            allowed_amount=170.0,
            is_anomalous=True,
        )
        prob_normal, _, _, _ = appeal.explain_line(
            cpt_code="99214",
            geography="NY",
            provider_type="primary_care",
            payer="payer_a",
            units=1.0,
            charge_amount=170.0,
            allowed_amount=170.0,
            is_anomalous=False,
        )
        assert prob_anomalous > prob_normal


class TestSyntheticData:
    def test_generates_expected_schema(self):
        gen = SyntheticDataGenerator(seed=42, n_samples=100)
        df = gen.generate()
        expected_cols = {
            "cpt_code",
            "geography",
            "provider_type",
            "payer",
            "units",
            "charge_amount",
            "allowed_amount",
            "fair_price",
            "charge_ratio",
            "error_type",
            "is_anomalous",
            "appeal_success",
        }
        assert expected_cols.issubset(set(df.columns))
        assert len(df) == 100
        # Both classes present
        assert df["is_anomalous"].nunique() == 2
        assert df["appeal_success"].nunique() == 2

    def test_anomalous_charges_have_higher_ratio(self):
        gen = SyntheticDataGenerator(seed=42, n_samples=500)
        df = gen.generate()
        anomalous = df[df["is_anomalous"] == 1]
        normal = df[df["is_anomalous"] == 0]
        assert anomalous["charge_ratio"].mean() > normal["charge_ratio"].mean()