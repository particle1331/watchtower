"""Build MLflow-tracked datasets from a source.

``mlflow.data.from_pandas(...)`` captures the source location, a content
**digest** (hash), and the schema, so a run records the *exact* data it consumed
rather than an implicit "latest table". This is the platform's data-versioning
mechanism — no separate DVC/LakeFS is introduced.
"""


import pandas as pd
from mlflow.data import from_pandas
from mlflow.data.pandas_dataset import PandasDataset


def load_csv(source: str, *, delimiter: str = ",") -> pd.DataFrame:
    """Read a CSV from an http(s) URL or local path into a DataFrame.

    Blob sources are readable over HTTPS with a data-plane role; pandas follows
    the URL directly. Kept deliberately small — the point is that *source* is a
    stable, loggable reference, not a one-off download step.
    """
    return pd.read_csv(source, delimiter=delimiter)


def tracked_dataset(
    df: pd.DataFrame,
    *,
    source: str,
    name: str,
    targets: str | None = None,
) -> PandasDataset:
    """Wrap a DataFrame as an MLflow dataset (source + digest + schema).

    Log it inside a run with ``mlflow.log_input(dataset, context="training")`` to
    attach reconstructable data lineage to the resulting registered version.
    """
    return from_pandas(df, source=source, name=name, targets=targets)
