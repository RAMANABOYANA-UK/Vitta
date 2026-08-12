"""Training script — trains both ML models on synthetic data and persists them.

Usage:
    python -m scripts.train_models [--force]

The models are persisted to `models/` and loaded at inference time by the
scoring service.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure the project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ml.models import train_all_models  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Train ML models on synthetic data")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force retraining even if models already exist",
    )
    args = parser.parse_args()

    logger.info("Training models (force=%s)...", args.force)
    metrics = train_all_models(force=args.force)

    for name, m in metrics.items():
        logger.info(
            "%s: accuracy=%.3f roc_auc=%.3f brier=%.3f",
            name,
            m.get("accuracy", 0),
            m.get("roc_auc", 0),
            m.get("brier_score", 0),
        )

    logger.info("Models trained and saved to models/")


if __name__ == "__main__":
    main()