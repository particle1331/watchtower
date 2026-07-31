"""Build and register a pyfunc LLM artifact in the self-hosted MLflow registry (docs/03).

Usage::

    from ml_platform.llm.artifact_builder import build_and_register

    version = build_and_register(
        registered_name="qa-assistant",
        prompt_yaml_path="prompts/qa.yaml",
        config_yaml_path="prompts/config.yaml",
        experiment="llm-qa",
        extra_pip_requirements=["httpx>=0.27", "pyyaml>=6.0"],
    )

The function returns the registered ``ModelVersion`` object.  Config/prompts
travel inside the artifact; secrets are never passed here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import mlflow
import mlflow.pyfunc
import pandas as pd
import yaml

from ml_platform.llm.model import (
    DEFAULT_CONFIG_YAML,
    DEFAULT_PROMPT_YAML,
    LLMPyfunc,
    make_signature,
)


def build_and_register(
    registered_name: str,
    *,
    prompt_yaml_path: str | Path | None = None,
    config_yaml_path: str | Path | None = None,
    experiment: str = "llm",
    extra_pip_requirements: list[str] | None = None,
    tags: dict[str, Any] | None = None,
) -> mlflow.entities.model_registry.ModelVersion:
    """Package prompt/config as a pyfunc artifact and register it.

    If ``prompt_yaml_path`` / ``config_yaml_path`` are None, writes minimal
    stubs so the function works out of the box for smoke tests.

    Returns the ``ModelVersion`` for the newly registered version.
    """
    tmp_dir = Path(mlflow.get_artifact_uri()).parent / "_llm_artifact_build"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Write or copy the prompt/config files into a temp staging dir.
    prompt_file = tmp_dir / "prompt.yaml"
    config_file = tmp_dir / "config.yaml"

    if prompt_yaml_path is not None:
        prompt_file.write_text(Path(prompt_yaml_path).read_text(encoding="utf-8"), encoding="utf-8")
    else:
        prompt_file.write_text(DEFAULT_PROMPT_YAML, encoding="utf-8")

    if config_yaml_path is not None:
        config_file.write_text(Path(config_yaml_path).read_text(encoding="utf-8"), encoding="utf-8")
    else:
        config_file.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")

    artifacts = {
        "prompt": str(prompt_file),
        "config": str(config_file),
    }

    pip_reqs = [
        "httpx>=0.27",
        "pyyaml>=6.0",
        "azure-identity>=1.17",
        "azure-keyvault-secrets>=4.8",
        *(extra_pip_requirements or []),
    ]

    with mlflow.start_run(tags={"artifact_type": "llm-pyfunc", **(tags or {})}):
        # Log the prompt/config files as run artefacts for lineage.
        mlflow.log_artifact(str(prompt_file), artifact_path="prompt")
        mlflow.log_artifact(str(config_file), artifact_path="config")

        # Log the prompt content as params for easy inspection.
        prompt_cfg: dict[str, Any] = yaml.safe_load(prompt_file.read_text())
        config_cfg: dict[str, Any] = yaml.safe_load(config_file.read_text())
        mlflow.log_param("model_endpoint", config_cfg.get("endpoint", ""))
        mlflow.log_param("model_id", config_cfg.get("generation", {}).get("model", ""))
        mlflow.log_param("temperature", config_cfg.get("generation", {}).get("temperature", 0.0))
        mlflow.log_param("system_prompt_len", len(prompt_cfg.get("system", "")))

        # Log and register the pyfunc.
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=LLMPyfunc(),
            artifacts=artifacts,
            signature=make_signature(),
            pip_requirements=pip_reqs,
            registered_model_name=registered_name,
        )

    # Return the ModelVersion for the caller to inspect or gate on.
    client = mlflow.MlflowClient()
    versions = client.search_model_versions(f"name='{registered_name}'")
    latest = max(versions, key=lambda v: int(v.version))
    return latest


def canary_predict(model_uri: str) -> pd.DataFrame:
    """Load a registered pyfunc version and run one prediction (smoke test)."""
    model = mlflow.pyfunc.load_model(model_uri)
    sample = pd.DataFrame([{"input": "What is 2 + 2?"}])
    return model.predict(sample)
