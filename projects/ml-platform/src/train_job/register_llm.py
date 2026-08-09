"""Package and register an LLM app as an MLflow pyfunc version (docs/03).

Usage (as an ACA Job or local script):
    python register_llm.py \\
        --prompt-yaml  prompts/qa.yaml \\
        --config-yaml  prompts/config.yaml \\
        --registered-name qa-assistant \\
        --experiment llm-qa

The script configures MLflow tracking, packages the pyfunc artifact, registers
it, and writes a results-DB record (``name='register_llm:<registered-name>'``).
Like train.py it is a no-op results record before Phase 2 (``PGHOST`` unset).
"""


import argparse
import os

from ml_platform.common.mlflow_client import configure_mlflow
from ml_platform.common.results import record_run
from ml_platform.llm.artifact_builder import build_and_register


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Package + register an LLM pyfunc version.")
    p.add_argument(
        "--prompt-yaml",
        default=None,
        help="Path to prompt.yaml; omit to use the built-in stub (smoke-test).",
    )
    p.add_argument(
        "--config-yaml",
        default=None,
        help="Path to config.yaml; omit to use the built-in stub.",
    )
    p.add_argument("--registered-name", default="llm-app", help="MLflow registered model name")
    p.add_argument("--experiment", default="llm", help="MLflow experiment name")
    p.add_argument(
        "--extra-pip",
        nargs="*",
        default=[],
        help="Extra pip requirements to include in the pyfunc artifact.",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    configure_mlflow(args.experiment)

    image_digest = os.environ.get("IMAGE_DIGEST", "unknown")

    with record_run(f"register_llm:{args.registered_name}") as rec:
        version = build_and_register(
            registered_name=args.registered_name,
            prompt_yaml_path=args.prompt_yaml,
            config_yaml_path=args.config_yaml,
            experiment=args.experiment,
            extra_pip_requirements=args.extra_pip,
            tags={"code.image_digest": image_digest},
        )
        rec["registered_name"] = args.registered_name
        rec["registered_version"] = version.version
        rec["run_id"] = version.run_id


if __name__ == "__main__":
    main()
