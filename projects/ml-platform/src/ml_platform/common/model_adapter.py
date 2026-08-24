"""Shared model loading and input/output adaptation (docs/05, docs/03).

The local Compose demo and the ACA workloads use the same MLflow model
artifacts.  ``pyfunc`` is the common loading interface: sklearn models expose
the same ``predict`` method through it, while LLM artifacts can use their
string-column signature without a separate serving path.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal, cast

import pandas as pd

ModelKind = Literal["tabular", "text"]


def model_kind(model: Any) -> ModelKind:
    """Infer the input shape from the stored MLflow signature.

    LLM artifacts created by ``artifact_builder`` have one input column named
    ``input``.  Classical models in this project do not store a signature, so
    they use the tabular fallback.
    """
    try:
        schema = model.metadata.get_input_schema()
        names = list(schema.input_names()) if schema is not None else []
    except (AttributeError, TypeError, ValueError):
        names = []
    return "text" if names == ["input"] else "tabular"


def frame_for_instances(model: Any, instances: Iterable[Any]) -> pd.DataFrame:
    """Convert API instances into the DataFrame expected by a model."""
    values = list(instances)
    if model_kind(model) == "text":
        if all(isinstance(value, str) for value in values):
            return pd.DataFrame({"input": values})
        if all(isinstance(value, dict) and "input" in value for value in values):
            return pd.DataFrame(values)
        raise ValueError("text models require string instances or {'input': ...} records")
    return pd.DataFrame(values)


def frame_for_batch(model: Any, frame: pd.DataFrame, target: str) -> pd.DataFrame:
    """Prepare a batch frame without removing an LLM's required input column."""
    if model_kind(model) == "text":
        if "input" not in frame.columns:
            raise ValueError("text models require an 'input' column in batch data")
        return cast(pd.DataFrame, frame[["input"]])
    return frame.drop(columns=[target], errors="ignore")


def prediction_values(predictions: Any) -> list[Any]:
    """Serialize sklearn scalars and pyfunc DataFrame records uniformly."""
    if isinstance(predictions, pd.DataFrame):
        return predictions.to_dict(orient="records")
    if isinstance(predictions, pd.Series):
        return predictions.tolist()
    if hasattr(predictions, "tolist"):
        values = predictions.tolist()
        return values if isinstance(values, list) else [values]
    return list(predictions)
