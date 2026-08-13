"""MLflow pyfunc PythonModel for an LLM app (docs/03).

The artifact bundles everything that defines the app:
  - ``prompt.yaml``  — system prompt + user template (Jinja2-compatible).
  - ``config.yaml``  — model endpoint reference + generation parameters.
  - any optional ``retrieval.yaml`` for index/RAG configuration.

At ``load_context`` the model reads these files from the MLflow artifacts
directory.  At ``predict`` it:
  1. Formats the user message via the prompt template.
  2. Calls the external model/API endpoint.
  3. Returns a uniform response dict.

No secrets are stored in the artifact.  The model endpoint credentials
(API key, Azure OpenAI token) are resolved at runtime from Key Vault via the
workload managed identity, or from the ``MODEL_API_KEY`` env var (local dev).

Input schema (MLflow signature enforces this):
  ``pandas.DataFrame`` with a single string column ``"input"``.

Output schema:
  ``pandas.DataFrame`` with columns ``["content", "model", "prompt_tokens",
  "completion_tokens"]``.
"""


import os
from typing import Any

import mlflow
import pandas as pd
import yaml


class LLMPyfunc(mlflow.pyfunc.PythonModel):
    """Self-contained LLM app packaged as an MLflow pyfunc."""

    def load_context(self, context: mlflow.pyfunc.PythonModelContext) -> None:
        artifacts = context.artifacts

        with open(artifacts["prompt"], encoding="utf-8") as f:
            self._prompt_cfg: dict[str, Any] = yaml.safe_load(f)

        with open(artifacts["config"], encoding="utf-8") as f:
            self._model_cfg: dict[str, Any] = yaml.safe_load(f)

        self._system_prompt: str = self._prompt_cfg.get("system", "")
        self._user_template: str = self._prompt_cfg.get("user_template", "{input}")
        self._endpoint: str = self._model_cfg["endpoint"]
        self._gen_params: dict[str, Any] = self._model_cfg.get("generation", {})

    def predict(
        self,
        context: mlflow.pyfunc.PythonModelContext,  # noqa: ARG002
        model_input: pd.DataFrame,
        params: dict[str, Any] | None = None,  # noqa: ARG002
    ) -> pd.DataFrame:
        results = [self._call_one(str(row)) for row in model_input["input"]]
        return pd.DataFrame(results)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_one(self, user_input: str) -> dict[str, Any]:
        formatted = self._user_template.replace("{input}", user_input)
        messages = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": formatted})

        return _call_openai_compat(
            endpoint=self._endpoint,
            messages=messages,
            gen_params=self._gen_params,
        )


# ---------------------------------------------------------------------------
# Provider-agnostic HTTP call (OpenAI-compatible /chat/completions)
# ---------------------------------------------------------------------------

def _call_openai_compat(
    endpoint: str,
    messages: list[dict[str, str]],
    gen_params: dict[str, Any],
) -> dict[str, Any]:
    """Call an OpenAI-compatible endpoint; credentials from env / Key Vault."""
    import httpx

    api_key = _resolve_api_key(endpoint)
    model_id = gen_params.get("model", "gpt-4o-mini")
    payload = {
        "model": model_id,
        "messages": messages,
        "temperature": gen_params.get("temperature", 0.0),
        "max_tokens": gen_params.get("max_tokens", 512),
    }

    resp = httpx.post(
        f"{endpoint.rstrip('/')}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    choice = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return {
        "content": choice,
        "model": data.get("model", model_id),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
    }


def _resolve_api_key(endpoint: str) -> str:
    """Prefer explicit env; fall back to Key Vault via managed identity."""
    key = os.environ.get("MODEL_API_KEY")
    if key:
        return key

    secret_name = os.environ.get("MODEL_API_KEY_SECRET", "model-api-key")
    vault_url = os.environ.get("KEY_VAULT_URL")
    if not vault_url:
        raise RuntimeError(
            "MODEL_API_KEY or KEY_VAULT_URL must be set to resolve model credentials."
        )

    from azure.identity import DefaultAzureCredential
    from azure.keyvault.secrets import SecretClient

    client = SecretClient(vault_url=vault_url, credential=DefaultAzureCredential())
    return client.get_secret(secret_name).value


# ---------------------------------------------------------------------------
# Signature helper (used by artifact_builder.py)
# ---------------------------------------------------------------------------

def make_signature() -> mlflow.models.ModelSignature:
    from mlflow.models.signature import ModelSignature
    from mlflow.types.schema import ColSpec, Schema

    return ModelSignature(
        inputs=Schema([ColSpec("string", "input")]),
        outputs=Schema([
            ColSpec("string", "content"),
            ColSpec("string", "model"),
            ColSpec("long", "prompt_tokens"),
            ColSpec("long", "completion_tokens"),
        ]),
    )


# ---------------------------------------------------------------------------
# Default prompt / config templates (written by artifact_builder.py)
# ---------------------------------------------------------------------------

DEFAULT_PROMPT_YAML = """\
# prompt.yaml — version-controlled prompt definition.
# Stored inside the pyfunc artifact; change → new registered version.
system: >
  You are a helpful assistant.
user_template: "{input}"
"""

DEFAULT_CONFIG_YAML = """\
# config.yaml — model endpoint + generation parameters.
# Credentials (API key) are resolved at runtime from Key Vault / env — never here.
endpoint: "https://api.openai.com/v1"
generation:
  model: "gpt-4o-mini"
  temperature: 0.0
  max_tokens: 512
"""
