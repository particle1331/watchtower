from types import SimpleNamespace

import pandas as pd
import pytest
from ml_platform.common.model_adapter import (
    frame_for_batch,
    frame_for_instances,
    model_kind,
    prediction_values,
)


class _Schema:
    def __init__(self, names: list[str]):
        self._names = names

    def input_names(self) -> list[str]:
        return self._names


def _model(names: list[str] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        metadata=SimpleNamespace(
            get_input_schema=lambda: _Schema(names) if names is not None else None
        )
    )


def test_model_kind_uses_text_signature() -> None:
    assert model_kind(_model(["input"])) == "text"
    assert model_kind(_model(["feature_a", "feature_b"])) == "tabular"
    assert model_kind(_model()) == "tabular"


def test_text_instances_become_input_column() -> None:
    frame = frame_for_instances(_model(["input"]), ["hello", "world"])
    assert frame.to_dict(orient="records") == [{"input": "hello"}, {"input": "world"}]

    records = frame_for_instances(_model(["input"]), [{"input": "hello"}])
    assert records.to_dict(orient="records") == [{"input": "hello"}]


def test_text_instances_reject_tabular_shape() -> None:
    with pytest.raises(ValueError, match="text models require"):
        frame_for_instances(_model(["input"]), [[1.0, 2.0]])


def test_batch_adapter_preserves_text_input_and_drops_tabular_target() -> None:
    source = pd.DataFrame({"input": ["a"], "quality": [5]})
    assert list(frame_for_batch(_model(["input"]), source, "quality")) == ["input"]

    tabular = pd.DataFrame({"feature": [1.0], "quality": [5]})
    assert list(frame_for_batch(_model(["feature"]), tabular, "quality")) == ["feature"]


def test_prediction_values_support_tabular_and_pyfunc_outputs() -> None:
    assert prediction_values(pd.Series([1.0, 2.0])) == [1.0, 2.0]
    assert prediction_values(pd.DataFrame({"content": ["ok"]})) == [{"content": "ok"}]
    assert prediction_values([1, 2]) == [1, 2]
