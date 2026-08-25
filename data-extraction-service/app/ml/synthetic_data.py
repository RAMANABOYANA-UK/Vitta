"""Synthetic data generator for ML model training.

Real billing data doesn't exist yet, so we generate synthetic data matching the
ParsedBill schema. The generator produces realistic charge/allowed/paid amounts,
CPT codes, provider types, geographies, and billing-error flags that mimic real
patterns (duplicates, unbundling, arithmetic errors, surprise billing).

Two target variables are generated:
  1. `is_anomalous` — a pricing-anomaly flag (charge is far from fair price)
  2. `appeal_success` — a binary appeal-success outcome

The generator has identifiable ground-truth structure so the models can learn
meaningful patterns and the SHAP explanations make sense.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

from app.config import settings


def _stable_hash(text: str) -> int:
    """Deterministic, process-independent hash of a string.

    Python's built-in ``hash()`` is salted per process (PYTHONHASHSEED), so it
    returns different values on every run. That caused train/serve skew: the
    ``fair_price`` feature (via ``_geo_factor``) was computed with one geo factor
    at training time and a *different* one in a fresh serving process, so a
    persisted model scored features drawn from a distribution it never saw. Using
    a fixed digest makes the synthetic features fully reproducible across
    processes while preserving the original "spread" semantics of ``% N``.
    """
    digest = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


# Reference CPT codes with approximate fair-price benchmarks (per unit, median)
# by geography and provider type. These are synthetic benchmarks for training.
CPT_FAIR_PRICE: Dict[str, float] = {
    "99201": 60.00,
    "99202": 110.00,
    "99203": 160.00,
    "99204": 220.00,
    "99205": 280.00,
    "99211": 40.00,
    "99212": 75.00,
    "99213": 120.00,
    "99214": 170.00,
    "99215": 230.00,
    "93000": 45.00,
    "93005": 35.00,
    "93010": 30.00,
    "80048": 35.00,
    "80053": 50.00,
    "80061": 55.00,
    "85025": 35.00,
    "81001": 30.00,
    "71045": 65.00,
    "71046": 90.00,
    "71250": 450.00,
    "70450": 400.00,
    "74150": 500.00,
    "76700": 200.00,
    "93306": 400.00,
    "36415": 20.00,
    "96372": 45.00,
    "90471": 30.00,
    "90658": 25.00,
    "20610": 200.00,
    "J1100": 30.00,
    "J2505": 6000.00,
    "J1885": 30.00,
}

GEOGRAPHIES: List[str] = ["NY", "CA", "TX", "FL", "IL", "WA", "MA", "CO", "GA", "NC"]
PROVIDER_TYPES: List[str] = [
    "primary_care",
    "specialist",
    "hospital",
    "outpatient_clinic",
    "laboratory",
    "radiology",
    "emergency",
    "physical_therapy",
]
PAYERS: List[str] = ["payer_a", "payer_b", "payer_c", "payer_d", "payer_e"]
ERROR_TYPES: List[str] = [
    "duplicate_charge",
    "unbundling",
    "arithmetic_mismatch",
    "surprise_billing",
    "none",
]


def _geo_factor(rng: np.random.Generator, geo: str) -> float:
    """Geography cost factor (deterministic-ish noise per geography)."""
    return 0.85 + 0.5 * (_stable_hash(geo) % 100) / 100.0


def _provider_factor(rng: np.random.Generator, prov: str) -> float:
    """Provider-type cost factor. Hospitals & ER bill higher."""
    factors = {
        "primary_care": 1.0,
        "specialist": 1.3,
        "hospital": 1.8,
        "outpatient_clinic": 1.2,
        "laboratory": 0.8,
        "radiology": 1.5,
        "emergency": 2.4,
        "physical_therapy": 1.1,
    }
    return factors.get(prov, 1.0)


def _base_fair_charge(cpt: str, geo: str, prov: str, rng: np.random.Generator) -> float:
    """Compute a fair reference charge given CPT, geo, and provider type."""
    base = CPT_FAIR_PRICE.get(cpt, 100.0)
    return base * _geo_factor(rng, geo) * _provider_factor(rng, prov)


class SyntheticDataGenerator:
    """Generates synthetic labeled data for model training."""

    def __init__(self, seed: Optional[int] = None, n_samples: Optional[int] = None):
        self.seed = seed if seed is not None else settings.synthetic_seed
        self.n_samples = n_samples if n_samples is not None else settings.synthetic_n_samples
        self.rng = np.random.default_rng(self.seed)

    def generate(self) -> pd.DataFrame:
        """Generate the full synthetic dataset."""
        n = self.n_samples
        rng = self.rng

        # === Base features ===
        cpts = rng.choice(list(CPT_FAIR_PRICE.keys()), size=n)
        geos = rng.choice(GEOGRAPHIES, size=n)
        prov_types = rng.choice(PROVIDER_TYPES, size=n)
        payers = rng.choice(PAYERS, size=n)

        # Units (some services are multi-unit)
        units = rng.choice([1, 1, 1, 1, 2, 2, 3, 4], size=n).astype(float)

        # Regional median charge for the (cpt, geo, prov) combo
        fair = np.array(
            [
                _base_fair_charge(c, g, p, rng)
                for c, g, p in zip(cpts, geos, prov_types)
            ]
        )

        # Allowed amount ≈ fair, with noise (payer contract discount)
        allowed = fair * rng.normal(1.0, 0.05, size=n)
        allowed = np.maximum(allowed, 0.0)

        # Error type (ground truth)
        # Normal docs are mostly error-free; a fraction have errors
        error_probs = [0.05, 0.03, 0.04, 0.02, 0.86]
        error_type = rng.choice(ERROR_TYPES, size=n, p=error_probs)

        # === Anomaly ground truth ===
        # charge deviates from fair; anomalous if error is one of billing errors or
        # charge is inflated
        charge = allowed * units * rng.normal(1.0, 0.10, size=n)
        is_anomalous_raw = np.zeros(n, dtype=bool)

        # Duplicate charge: charge ≈ 2x expected
        dup_mask = error_type == "duplicate_charge"
        charge[dup_mask] = fair[dup_mask] * units[dup_mask] * 2.0 * rng.normal(1.0, 0.05, size=dup_mask.sum())
        is_anomalous_raw[dup_mask] = True

        # Unbundling: effectively higher total charge
        unb_mask = error_type == "unbundling"
        charge[unb_mask] = fair[unb_mask] * units[unb_mask] * 1.6 * rng.normal(1.0, 0.05, size=unb_mask.sum())
        is_anomalous_raw[unb_mask] = True

        # Arithmetic mismatch: totals don't add up (captured elsewhere, but
        # slightly inflates charge signal)
        arith_mask = error_type == "arithmetic_mismatch"
        charge[arith_mask] = fair[arith_mask] * units[arith_mask] * 1.1 * rng.normal(1.0, 0.05, size=arith_mask.sum())
        is_anomalous_raw[arith_mask] = True

        # Surprise billing: bill from out-of-network provider with high charge
        surprise_mask = error_type == "surprise_billing"
        charge[surprise_mask] = fair[surprise_mask] * units[surprise_mask] * 4.0 * rng.normal(1.0, 0.1, size=surprise_mask.sum())
        is_anomalous_raw[surprise_mask] = True

        # Also mark very-high-charge (even without an explicit error) as anomalous
        # charge_ratio > 2.5x fair is always anomalous
        ratio = charge / np.maximum(fair, 1e-6)
        is_anomalous_raw |= (ratio > 2.5)

        is_anomalous = is_anomalous_raw.astype(int)

        # === Appeal success ground truth ===
        # Success is more likely when there IS an actual billing error and the
        # anomaly ratio is high, and less likely when the charge is near-normal.
        # Add noise so the model learns probability, not a deterministic rule.

        # Base success prob from error type
        err_success_base = {
            "duplicate_charge": 0.75,
            "unbundling": 0.65,
            "arithmetic_mismatch": 0.55,
            "surprise_billing": 0.85,
            "none": 0.15,
        }
        success_prob = np.array([err_success_base[e] for e in error_type], dtype=float)

        # Modulate by ratio: the more egregious, the higher the chance (up to a point)
        ratio_norm = np.clip((ratio - 1.0) / 3.0, 0, 1)
        success_prob = success_prob + 0.15 * ratio_norm

        # Modulate by geo/payer 'friendliness' noise
        geo_noise = np.array([(_stable_hash(g) % 20) / 100.0 for g in geos])
        payer_noise = np.array([(_stable_hash(p) % 15) / 100.0 for p in payers])
        success_prob = np.clip(success_prob + geo_noise - payer_noise, 0.02, 0.98)

        appeal_success = (rng.random(n) < success_prob).astype(int)

        # === Output feature matrix ===
        df = pd.DataFrame(
            {
                "cpt_code": cpts,
                "geography": geos,
                "provider_type": prov_types,
                "payer": payers,
                "units": units,
                "charge_amount": np.round(charge, 2),
                "allowed_amount": np.round(allowed, 2),
                "fair_price": np.round(fair, 2),
                "charge_ratio": np.round(ratio, 3),
                "error_type": error_type,
                "is_anomalous": is_anomalous,
                "appeal_success": appeal_success,
            }
        )
        return df

    def features_for_line(
        self,
        cpt_code: str,
        geography: str = "NY",
        provider_type: str = "primary_care",
        payer: str = "payer_a",
        units: float = 1.0,
        charge_amount: Optional[float] = None,
        allowed_amount: Optional[float] = None,
    ) -> pd.DataFrame:
        """Build a single-row feature DataFrame for one line item (for inference)."""
        fair = _base_fair_charge(cpt_code, geography, provider_type, self.rng)
        charge = charge_amount if charge_amount is not None else fair * units
        allowed = allowed_amount if allowed_amount is not None else fair * units * 0.9
        ratio = charge / max(fair, 1e-6)

        # Encode provider type / geo / payer as categorical numeric features
        # (matched to the training encoding)
        prov_codes = {p: i for i, p in enumerate(PROVIDER_TYPES)}
        geo_codes = {g: i for i, g in enumerate(GEOGRAPHIES)}
        payer_codes = {p: i for i, p in enumerate(PAYERS)}

        return pd.DataFrame(
            [
                {
                    "cpt_code": cpt_code,
                    "geography": geography,
                    "provider_type": provider_type,
                    "payer": payer,
                    "units": units,
                    "charge_amount": round(charge, 2),
                    "allowed_amount": round(allowed, 2),
                    "fair_price": round(fair, 2),
                    "charge_ratio": round(ratio, 3),
                    "prov_type_code": prov_codes.get(provider_type, 0),
                    "geo_code": geo_codes.get(geography, 0),
                    "payer_code": payer_codes.get(payer, 0),
                }
            ]
        )