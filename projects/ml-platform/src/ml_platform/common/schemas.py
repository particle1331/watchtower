"""Boundary data validation with Pandera (docs/02).

Input data is validated at the **start** of a job, before training, so malformed
data fails fast with a clear error (and a ``FAILURE`` results-DB record) rather
than silently training on garbage. The wine-quality schema below matches the
runnable demonstration in docs/02; real workloads swap in their own contract.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

# Physicochemical features + integer quality score (UCI wine-quality, white).
_UNIT_INTERVAL_FLOAT = pa.Column(float, pa.Check.ge(0), nullable=False)

wine_quality_schema = pa.DataFrameSchema(
    {
        "fixed acidity": _UNIT_INTERVAL_FLOAT,
        "volatile acidity": _UNIT_INTERVAL_FLOAT,
        "citric acid": _UNIT_INTERVAL_FLOAT,
        "residual sugar": _UNIT_INTERVAL_FLOAT,
        "chlorides": _UNIT_INTERVAL_FLOAT,
        "free sulfur dioxide": _UNIT_INTERVAL_FLOAT,
        "total sulfur dioxide": _UNIT_INTERVAL_FLOAT,
        "density": _UNIT_INTERVAL_FLOAT,
        "pH": pa.Column(float, pa.Check.in_range(0, 14)),
        "sulphates": _UNIT_INTERVAL_FLOAT,
        "alcohol": _UNIT_INTERVAL_FLOAT,
        "quality": pa.Column(int, pa.Check.in_range(0, 10)),
    },
    strict=False,  # tolerate extra columns; enforce the known ones
    coerce=True,
)


def validate(
    df: pd.DataFrame,
    schema: pa.DataFrameSchema = wine_quality_schema,
) -> pd.DataFrame:
    """Validate ``df`` against ``schema``, collecting all failures at once.

    Raises ``pandera.errors.SchemaErrors`` on violation so the caller can fail
    the run early with the full report.
    """
    return schema.validate(df, lazy=True)
