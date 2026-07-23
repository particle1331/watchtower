"""Data validation with Pandera.

Schemas run at extraction time and before training. Failures stop the pipeline.
Reports are logged to MLflow.

See: learning/mlops/04-data-validation.ipynb
"""

import logging

import mlflow
import pandas as pd
import pandera as pa
from pandera.typing import DataFrame, Series

from pandera.errors import SchemaErrors

logger = logging.getLogger(__name__)


class RawDocumentSchema(pa.DataFrameModel):
    """Schema for raw documents before feature engineering."""

    doc_id: Series[str] = pa.Field(nullable=False, unique=True)
    content: Series[str] = pa.Field(nullable=False)
    category: Series[str] = pa.Field(isin=["news", "tech", "finance", "health", "other"])
    created_at: Series[pd.Timestamp] = pa.Field(nullable=False)
    word_count: Series[int] = pa.Field(ge=1)


class TrainingFeaturesSchema(pa.DataFrameModel):
    """Schema for training features after feature engineering."""

    feature_a: Series[float] = pa.Field(nullable=False)
    feature_b: Series[float] = pa.Field(nullable=False)
    feature_c: Series[float] = pa.Field(nullable=False)
    label: Series[int] = pa.Field(isin=[0, 1])


def validate_raw_documents(df: pd.DataFrame) -> DataFrame[RawDocumentSchema]:
    """Validate raw documents against the schema. Raises on failure."""
    try:
        validated = RawDocumentSchema.validate(df, lazy=True)
        logger.info("Raw document validation passed: %d rows", len(validated))
        return validated
    except SchemaErrors as e:
        logger.error("Raw document validation failed: %s", e)
        raise


def validate_training_features(
    df: pd.DataFrame,
    mlflow_run: mlflow.ActiveRun | None = None,
) -> DataFrame[TrainingFeaturesSchema]:
    """Validate training features. If an MLflow run is active, log a report."""
    try:
        validated = TrainingFeaturesSchema.validate(df, lazy=True)
        logger.info("Training feature validation passed: %d rows", len(validated))
        if mlflow_run:
            mlflow.log_dict(
                {"status": "passed", "rows": len(validated), "columns": list(validated.columns)},
                "validation/training_features.json",
            )
        return validated
    except SchemaErrors as e:
        logger.error("Training feature validation failed: %s", e)
        if mlflow_run:
            mlflow.log_dict(
                {
                    "status": "failed",
                    "error": str(e),
                    "failure_cases": e.failure_cases.to_dict() if hasattr(e, "failure_cases") else None,
                },
                "validation/training_features.json",
            )
        raise
