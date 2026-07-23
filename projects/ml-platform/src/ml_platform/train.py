"""Training entry point.

Generates synthetic demo data, validates it with Pandera, trains the pipeline,
registers the model in MLflow, and promotes it via alias.

Usage:
    make train          # from project root
    uv run python -m ml_platform.train
"""

import logging

import numpy as np
import pandas as pd

from ml_platform.model_pipeline import train_and_log
from ml_platform.validate import validate_training_features

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def generate_demo_data(n_samples: int = 200) -> pd.DataFrame:
    """Generate synthetic training data for the demo."""
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "feature_a": rng.normal(0, 1, n_samples),
            "feature_b": rng.normal(0.5, 1.5, n_samples),
            "feature_c": rng.exponential(1, n_samples),
            "label": rng.integers(0, 2, n_samples),
        }
    )


def main() -> None:
    logger.info("Generating demo training data")
    df = generate_demo_data()

    logger.info("Validating training features")
    validate_training_features(df)

    logger.info("Training pipeline and logging to MLflow")
    run_id, version = train_and_log(df)
    logger.info("Done — run=%s model_version=%s", run_id, version)
    logger.info("Visit http://localhost:5000 to see the run and registered model")


if __name__ == "__main__":
    main()
