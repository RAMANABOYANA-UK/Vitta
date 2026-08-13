"""ML models — pricing-anomaly and appeal-success classifiers.

Both models are XGBoost classifiers with probability calibration
(CalibratedClassifierCV with isotonic regression) so they output calibrated
probabilities, never raw scores. SHAP is used for explainability, producing
clean, human-readable key-value feature contributions pre-formatted for a
downstream LLM to quote directly.

Models are trained on synthetic data (see synthetic_data.py) since real billing
data doesn't exist yet. They are persisted to `models/` and loaded at inference.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from sklearn.calibration import CalibratedClassifierCV
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

from app.config import settings
from app.ml.synthetic_data import (
    CPT_FAIR_PRICE,
    GEOGRAPHIES,
    PAYERS,
    PROVIDER_TYPES,
    SyntheticDataGenerator,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
# Numeric features used by both models (after encoding categoricals)
NUMERIC_FEATURES = [
    "units",
    "charge_amount",
    "allowed_amount",
    "fair_price",
    "charge_ratio",
    "prov_type_code",
    "geo_code",
    "payer_code",
]

# Appeal model additionally uses the anomaly flag as a feature
APPEAL_FEATURES = NUMERIC_FEATURES + ["is_anomalous"]

# Human-readable feature names for SHAP explanations
FEATURE_LABELS = {
    "units": "units",
    "charge_amount": "charge amount",
    "allowed_amount": "allowed amount",
    "fair_price": "regional fair price",
    "charge_ratio": "charge-to-fair-price ratio",
    "prov_type_code": "provider type",
    "geo_code": "geography",
    "payer_code": "payer",
}


def _encode_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    """Encode categorical features as numeric codes for the models."""
    out = df.copy()
    prov_codes = {p: i for i, p in enumerate(PROVIDER_TYPES)}
    geo_codes = {g: i for i, g in enumerate(GEOGRAPHIES)}
    payer_codes = {p: i for i, p in enumerate(PAYERS)}
    out["prov_type_code"] = out["provider_type"].map(prov_codes).fillna(0).astype(int)
    out["geo_code"] = out["geography"].map(geo_codes).fillna(0).astype(int)
    out["payer_code"] = out["payer"].map(payer_codes).fillna(0).astype(int)
    return out


def _feature_matrix(df: pd.DataFrame, feature_names: Optional[List[str]] = None) -> pd.DataFrame:
    """Return the numeric feature matrix used for training/inference."""
    cols = feature_names or NUMERIC_FEATURES
    return df[cols].copy()


# ---------------------------------------------------------------------------
# Base model wrapper
# ---------------------------------------------------------------------------
class _BaseModel:
    """Shared training/persistence logic for the two models."""

    def __init__(self, name: str, feature_names: Optional[List[str]] = None):
        self.name = name
        self.model: Optional[xgb.XGBClassifier] = None
        self.calibrator: Optional[IsotonicRegression] = None
        self.explainer: Optional[shap.TreeExplainer] = None
        self.feature_names: List[str] = feature_names or NUMERIC_FEATURES
        self.metrics: Dict[str, float] = {}
        self.trained = False

    # --- Persistence ---
    @property
    def model_path(self) -> Path:
        return Path(settings.models_dir) / f"{self.name}_model.json"

    @property
    def calibrator_path(self) -> Path:
        return Path(settings.models_dir) / f"{self.name}_calibrator.joblib"

    @property
    def metrics_path(self) -> Path:
        return Path(settings.models_dir) / f"{self.name}_metrics.json"

    def save(self) -> None:
        """Persist the model, calibrator, and metrics to disk."""
        Path(settings.models_dir).mkdir(parents=True, exist_ok=True)
        if self.model is None:
            raise RuntimeError(f"Cannot save {self.name}: model not trained")
        self.model.save_model(str(self.model_path))
        if self.calibrator is not None:
            joblib.dump(self.calibrator, self.calibrator_path)
        with open(self.metrics_path, "w") as f:
            json.dump(self.metrics, f, indent=2)
        logger.info("Saved %s model to %s", self.name, self.model_path)

    def load(self) -> bool:
        """Load a persisted model + calibrator. Returns True if loaded successfully."""
        if not self.model_path.exists():
            logger.warning("No persisted model found for %s at %s", self.name, self.model_path)
            return False
        try:
            base = xgb.XGBClassifier()
            base.load_model(str(self.model_path))
            self.model = base
            if self.calibrator_path.exists():
                self.calibrator = joblib.load(self.calibrator_path)
            self.explainer = shap.TreeExplainer(base)
            self.trained = True
            if self.metrics_path.exists():
                with open(self.metrics_path) as f:
                    self.metrics = json.load(f)
            logger.info("Loaded %s model from %s", self.name, self.model_path)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to load %s model: %s", self.name, exc)
            return False

    # --- Training ---
    def train(self, df: pd.DataFrame, target_col: str) -> Dict[str, float]:
        """Train the model on the given dataframe. Returns metrics."""
        df = _encode_categoricals(df)
        X = _feature_matrix(df, self.feature_names)
        y = df[target_col].astype(int)

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=settings.synthetic_seed, stratify=y
        )

        base = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=settings.synthetic_seed,
            eval_metric="logloss",
            use_label_encoder=False,
        )
        base.fit(X_train, y_train)

        # Fit isotonic calibration on a held-out validation split so the
        # calibrated probabilities are never raw scores.
        X_train_cal, X_cal, y_train_cal, y_cal = train_test_split(
            X_train, y_train, test_size=0.2, random_state=settings.synthetic_seed
        )
        base_cal = xgb.XGBClassifier(
            n_estimators=200,
            max_depth=5,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=settings.synthetic_seed,
            eval_metric="logloss",
            use_label_encoder=False,
        )
        base_cal.fit(X_train_cal, y_train_cal)
        raw_cal = base_cal.predict_proba(X_cal)[:, 1]
        calibrator = IsotonicRegression(out_of_bounds="clip")
        calibrator.fit(raw_cal, y_cal)

        self.model = base
        self.calibrator = calibrator
        self.trained = True

        # Build SHAP explainer on the base estimator
        self.explainer = shap.TreeExplainer(base)

        # Evaluate (apply calibration)
        raw_test = base.predict_proba(X_test)[:, 1]
        y_prob = calibrator.predict(raw_test)
        y_pred = (y_prob >= 0.5).astype(int)

        self.metrics = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "roc_auc": float(roc_auc_score(y_test, y_prob)),
            "brier_score": float(brier_score_loss(y_test, y_prob)),
            "log_loss": float(log_loss(y_test, y_prob)),
            "n_samples": int(len(df)),
            "n_positive": int(y.sum()),
            "n_negative": int((1 - y).sum()),
        }
        logger.info(
            "%s trained: accuracy=%.3f roc_auc=%.3f brier=%.3f",
            self.name,
            self.metrics["accuracy"],
            self.metrics["roc_auc"],
            self.metrics["brier_score"],
        )
        return self.metrics

    # --- Inference ---
    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """Return calibrated probability of the positive class (never raw scores)."""
        if self.model is None:
            raise RuntimeError(f"{self.name} model not trained/loaded")
        X = _feature_matrix(features, self.feature_names)
        raw = self.model.predict_proba(X)[:, 1]
        if self.calibrator is not None:
            return self.calibrator.predict(raw)
        return raw

    def predict(self, features: pd.DataFrame, threshold: float = 0.5) -> np.ndarray:
        return (self.predict_proba(features) >= threshold).astype(int)

    # --- SHAP ---
    def shap_values(self, features: pd.DataFrame) -> List[Dict[str, Any]]:
        """Return SHAP values for each row as a list of dicts keyed by feature."""
        if self.explainer is None:
            raise RuntimeError(f"{self.name} explainer not initialized")
        X = _feature_matrix(features, self.feature_names)
        shap_values = self.explainer.shap_values(X)
        # shap_values shape: (n_rows, n_features)
        results = []
        for i in range(X.shape[0]):
            row = {}
            for j, feat in enumerate(self.feature_names):
                row[feat] = float(shap_values[i, j])
            results.append(row)
        return results


# ---------------------------------------------------------------------------
# Pricing anomaly model
# ---------------------------------------------------------------------------
class PricingAnomalyModel(_BaseModel):
    """Flags charges anomalous relative to fair-price benchmarks."""

    def __init__(self):
        super().__init__("pricing_anomaly")

    def train(self, df: pd.DataFrame) -> Dict[str, float]:
        return super().train(df, target_col="is_anomalous")

    def explain_line(
        self,
        cpt_code: str,
        geography: str,
        provider_type: str,
        payer: str,
        units: float,
        charge_amount: float,
        allowed_amount: float,
    ) -> Tuple[float, float, bool, List[Dict[str, Any]]]:
        """Score a single line and produce SHAP explanations.

        Returns (calibrated_probability, score, is_anomalous, shap_explanations).
        """
        gen = SyntheticDataGenerator()
        features = gen.features_for_line(
            cpt_code=cpt_code,
            geography=geography,
            provider_type=provider_type,
            payer=payer,
            units=units,
            charge_amount=charge_amount,
            allowed_amount=allowed_amount,
        )
        prob = float(self.predict_proba(features)[0])
        threshold = settings.anomaly_threshold
        is_anomalous = prob >= threshold

        shap_rows = self.shap_values(features)
        shap_row = shap_rows[0] if shap_rows else {}

        # Actual charge-to-fair-price ratio (from the feature, not SHAP value)
        actual_ratio = float(features["charge_ratio"].iloc[0])

        # Build human-readable explanations
        explanations = self._build_explanations(
            shap_row,
            cpt_code,
            geography,
            provider_type,
            charge_amount,
            actual_ratio,
        )

        return prob, prob, is_anomalous, explanations

    def _build_explanations(
        self,
        shap_row: Dict[str, float],
        cpt_code: str,
        geography: str,
        provider_type: str,
        charge_amount: float,
        actual_ratio: float,
    ) -> List[Dict[str, Any]]:
        """Convert raw SHAP values into clean, human-readable key-value
        contributions pre-formatted for a downstream LLM."""
        explanations = []
        # Sort by absolute contribution, descending
        sorted_feats = sorted(
            shap_row.items(), key=lambda kv: abs(kv[1]), reverse=True
        )
        for feat, contrib in sorted_feats[:5]:  # top 5 features
            if abs(contrib) < 1e-6:
                continue
            direction = "increases_anomaly" if contrib > 0 else "decreases_anomaly"
            label = FEATURE_LABELS.get(feat, feat)

            # Build a human-readable sentence
            if feat == "charge_ratio":
                ratio = actual_ratio
                human = (
                    f"charge is {ratio:.1f}x the regional median for CPT {cpt_code}"
                    if ratio >= 1.0
                    else f"charge is {1/ratio:.1f}x below the regional median for CPT {cpt_code}"
                )
            elif feat == "charge_amount":
                human = f"charge amount of ${charge_amount:,.2f} is {'high' if contrib > 0 else 'low'} relative to fair price"
            elif feat == "fair_price":
                human = f"regional fair price for CPT {cpt_code} in {geography} ({provider_type})"
            elif feat == "prov_type_code":
                human = f"provider type ({provider_type})"
            elif feat == "geo_code":
                human = f"geography ({geography})"
            elif feat == "payer_code":
                human = f"payer contract"
            elif feat == "units":
                human = f"units billed"
            elif feat == "allowed_amount":
                human = f"allowed amount"
            else:
                human = f"{label}"

            explanations.append(
                {
                    "feature": feat,
                    "contribution": round(contrib, 4),
                    "direction": direction,
                    "human_readable": human,
                }
            )
        return explanations


# ---------------------------------------------------------------------------
# Appeal success model
# ---------------------------------------------------------------------------
class AppealSuccessModel(_BaseModel):
    """Predicts the probability of appeal success."""

    def __init__(self):
        super().__init__("appeal_success", feature_names=APPEAL_FEATURES)

    def train(self, df: pd.DataFrame) -> Dict[str, float]:
        return super().train(df, target_col="appeal_success")

    def explain_line(
        self,
        cpt_code: str,
        geography: str,
        provider_type: str,
        payer: str,
        units: float,
        charge_amount: float,
        allowed_amount: float,
        is_anomalous: bool,
    ) -> Tuple[float, float, str, List[Dict[str, Any]]]:
        """Score appeal success for a line and produce SHAP explanations.

        Returns (calibrated_probability, score, recommendation, shap_explanations).
        """
        gen = SyntheticDataGenerator()
        features = gen.features_for_line(
            cpt_code=cpt_code,
            geography=geography,
            provider_type=provider_type,
            payer=payer,
            units=units,
            charge_amount=charge_amount,
            allowed_amount=allowed_amount,
        )
        # Add anomaly signal as a feature (the appeal model benefits from knowing
        # whether the charge was flagged anomalous)
        features["is_anomalous"] = int(is_anomalous)

        prob = float(self.predict_proba(features)[0])

        # Recommendation based on calibrated probability
        if prob >= settings.appeal_threshold_strong:
            recommendation = "strong_appeal"
        elif prob >= settings.appeal_threshold_moderate:
            recommendation = "moderate_appeal"
        elif prob >= 0.3:
            recommendation = "weak_appeal"
        else:
            recommendation = "no_appeal"

        shap_rows = self.shap_values(features)
        shap_row = shap_rows[0] if shap_rows else {}

        # Actual charge-to-fair-price ratio (from the feature, not SHAP value)
        actual_ratio = float(features["charge_ratio"].iloc[0])

        explanations = self._build_explanations(
            shap_row,
            cpt_code,
            geography,
            provider_type,
            charge_amount,
            is_anomalous,
            actual_ratio,
        )

        return prob, prob, recommendation, explanations

    def _build_explanations(
        self,
        shap_row: Dict[str, float],
        cpt_code: str,
        geography: str,
        provider_type: str,
        charge_amount: float,
        is_anomalous: bool,
        actual_ratio: float,
    ) -> List[Dict[str, Any]]:
        explanations = []
        sorted_feats = sorted(
            shap_row.items(), key=lambda kv: abs(kv[1]), reverse=True
        )
        for feat, contrib in sorted_feats[:5]:
            if abs(contrib) < 1e-6:
                continue
            direction = "increases_success" if contrib > 0 else "decreases_success"
            label = FEATURE_LABELS.get(feat, feat)

            if feat == "is_anomalous":
                human = (
                    "charge was flagged as a billing anomaly (strong basis for appeal)"
                    if is_anomalous
                    else "charge was not flagged as anomalous (weaker appeal basis)"
                )
            elif feat == "charge_ratio":
                ratio = actual_ratio
                human = f"charge is {ratio:.1f}x the regional median for CPT {cpt_code}"
            elif feat == "charge_amount":
                human = f"charge amount of ${charge_amount:,.2f}"
            elif feat == "fair_price":
                human = f"regional fair price for CPT {cpt_code} in {geography}"
            elif feat == "prov_type_code":
                human = f"provider type ({provider_type})"
            elif feat == "geo_code":
                human = f"geography ({geography})"
            elif feat == "payer_code":
                human = f"payer contract"
            else:
                human = label

            explanations.append(
                {
                    "feature": feat,
                    "contribution": round(contrib, 4),
                    "direction": direction,
                    "human_readable": human,
                }
            )
        return explanations


# ---------------------------------------------------------------------------
# Training entrypoint
# ---------------------------------------------------------------------------
def train_all_models(force: bool = False) -> Dict[str, Dict[str, float]]:
    """Train both models on synthetic data and persist them.

    Returns a dict of model name -> metrics.
    """
    gen = SyntheticDataGenerator()
    df = gen.generate()

    anomaly_model = PricingAnomalyModel()
    appeal_model = AppealSuccessModel()

    # Only train if not already persisted (unless force)
    if force or not anomaly_model.model_path.exists():
        anomaly_metrics = anomaly_model.train(df)
        anomaly_model.save()
    else:
        anomaly_model.load()
        anomaly_metrics = anomaly_model.metrics

    if force or not appeal_model.model_path.exists():
        appeal_metrics = appeal_model.train(df)
        appeal_model.save()
    else:
        appeal_model.load()
        appeal_metrics = appeal_model.metrics

    return {
        "pricing_anomaly": anomaly_metrics,
        "appeal_success": appeal_metrics,
    }


def get_models() -> Tuple[PricingAnomalyModel, AppealSuccessModel]:
    """Load (or train if missing) and return both models."""
    anomaly = PricingAnomalyModel()
    appeal = AppealSuccessModel()

    if not anomaly.load():
        logger.info("Training pricing anomaly model...")
        gen = SyntheticDataGenerator()
        df = gen.generate()
        anomaly.train(df)
        anomaly.save()

    if not appeal.load():
        logger.info("Training appeal success model...")
        gen = SyntheticDataGenerator()
        df = gen.generate()
        appeal.train(df)
        appeal.save()

    return anomaly, appeal