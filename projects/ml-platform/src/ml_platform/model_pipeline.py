"""ML pipeline: feature engineering, training, packaging, and registration.

The pipeline is packaged as an MLflow model so preprocessing travels with the
model artifact — no separate feature store or learned-parameter files needed.

See: learning/mlops/05-ml-pipeline.ipynb
"""

import logging

import mlflow
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def build_pipeline() -> Pipeline:
    """Build a scikit-learn pipeline with preprocessing and classifier.

    Returns a pipeline that:
    1. Scales numeric features (feature_a, feature_b, feature_c)
    2. Trains a RandomForest classifier
    """
    numeric_features = ["feature_a", "feature_b", "feature_c"]

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), numeric_features),
        ],
        remainder="drop",
    )

    pipeline = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", RandomForestClassifier(n_estimators=50, random_state=42)),
        ]
    )

    return pipeline


def train_and_log(
    train_df: pd.DataFrame,
    experiment_name: str = "ml-platform-demo",
    run_name: str = "train",
) -> tuple[str, int | None]:
    """Train the pipeline, log to MLflow, and register the model.

    Args:
        train_df: DataFrame with feature columns + 'label' column.
        experiment_name: MLflow experiment name.
        run_name: Human-readable run name.

    Returns:
        (run_id, model_version) tuple.
    """
    mlflow.set_experiment(experiment_name)

    X = train_df[["feature_a", "feature_b", "feature_c"]]
    y = train_df["label"]

    pipeline = build_pipeline()

    with mlflow.start_run(run_name=run_name) as run:
        # Log dataset info
        mlflow.log_param("n_samples", len(train_df))
        mlflow.log_param("n_features", X.shape[1])
        mlflow.log_param("pipeline_steps", "StandardScaler + RandomForestClassifier")
        mlflow.log_param("random_state", 42)
        mlflow.log_param("n_estimators", 50)

        # Log label distribution
        mlflow.log_dict(
            y.value_counts().to_dict(),
            "artifacts/label_distribution.json",
        )

        # Train
        pipeline.fit(X, y)

        # Evaluate on training set (stub — real pipeline uses train/test split)
        train_score = pipeline.score(X, y)
        mlflow.log_metric("train_accuracy", train_score)
        logger.info("Training accuracy: %.4f", train_score)

        # Package pipeline as MLflow model
        signature = mlflow.models.infer_signature(  # pyright: ignore[reportPrivateImportUsage]
            X.head(1),
            pipeline.predict(X.head(1)),
        )

        model_info = mlflow.sklearn.log_model(  # pyright: ignore[reportPrivateImportUsage]
            sk_model=pipeline,
            artifact_path="model",
            signature=signature,
            registered_model_name="ml-platform-classifier",
        )

        mlflow.set_tag("git_branch", "main")
        mlflow.set_tag("model_type", "RandomForestClassifier")

        logger.info(
            "Model logged: run=%s version=%s",
            run.info.run_id,
            model_info.registered_model_version,
        )
        return run.info.run_id, model_info.registered_model_version
