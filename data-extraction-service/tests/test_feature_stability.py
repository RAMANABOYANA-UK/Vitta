"""Regression test for P0 #2 — synthetic ML features must be process-stable.

`_geo_factor` fed the `fair_price` feature through Python's built-in ``hash()``,
which is salted per process via PYTHONHASHSEED. A model persisted after training
was therefore served a `fair_price` computed from a *different* geo factor in a
fresh serving process — train/serve skew that silently degraded scoring.

The definitive check is cross-process: compute the feature in two subprocesses
under different PYTHONHASHSEED values and require identical output. This test
FAILS against the old hash()-based code and PASSES with the stable digest.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.ml.synthetic_data import _base_fair_charge, _stable_hash

_SERVICE_ROOT = Path(__file__).resolve().parents[1]


def test_stable_hash_is_deterministic_and_discriminating() -> None:
    assert _stable_hash("NY") == _stable_hash("NY")
    assert _stable_hash("NY") != _stable_hash("CA")


def _fair_price_in_subprocess(hashseed: str) -> float:
    code = (
        "import numpy as np;"
        "from app.ml.synthetic_data import _base_fair_charge;"
        "rng = np.random.default_rng(0);"
        "print(repr(_base_fair_charge('99213', 'NY', 'primary_care', rng)))"
    )
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = hashseed
    out = subprocess.check_output(
        [sys.executable, "-c", code],
        env=env,
        cwd=str(_SERVICE_ROOT),
        text=True,
    )
    return float(out.strip())


def test_fair_price_feature_is_process_independent() -> None:
    seed_a = _fair_price_in_subprocess("0")
    seed_b = _fair_price_in_subprocess("12345")
    assert seed_a == seed_b, (
        f"fair_price differs across PYTHONHASHSEED ({seed_a} vs {seed_b}); "
        "train/serve skew has regressed"
    )
    # And the subprocess value matches this process (also a fresh interpreter
    # from the subprocess's point of view).
    import numpy as np

    in_process = _base_fair_charge("99213", "NY", "primary_care", np.random.default_rng(0))
    assert in_process == seed_a
