"""Env-var drift detector: src/ consumers vs demo/docker-compose.yml providers.

Every environment variable an image under src/ reads must be provided by the
local Compose demo; otherwise a workflow that works in production silently
misconfigures the POC (or the reverse). This script walks src/**/*.py,
extracts os.environ reads, parses the compose environment blocks, and reports:

  - variables provided by compose (consuming files and providing services)
  - allow-listed variables that only production deployment definitions inject
    (each with its injector documented in ALLOWED_MISSING below)
  - MISSING variables: consumed somewhere under src/, provided nowhere

Exit code 1 when anything is missing.

The compose parser covers the YAML subset this repo uses: mapping-style
``environment`` blocks, one anchor (``environment: &job-environment`` on the
train service) expanded through a merge key (``<<: *job-environment``).

Usage:
    python tools/check_env_contract.py
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
COMPOSE_FILE = PROJECT_ROOT / "demo" / "docker-compose.yml"

# Variables intentionally absent from the Compose demo. Each entry documents
# who injects the variable in production-style deployments.
ALLOWED_MISSING: dict[str, str] = {
    # Dashboard production configuration, set on the ACA App definition.
    "AZURE_SUBSCRIPTION_ID": "dashboard ACA App definition (production)",
    "AZURE_RESOURCE_GROUP": "dashboard ACA App definition (production)",
    "TRAIN_JOB_NAME": "dashboard ACA App definition from Terraform output",
    "EVAL_JOB_NAME": "dashboard ACA App definition from Terraform output",
    "BATCH_JOB_NAME": "dashboard ACA App definition from Terraform output",
    "DASHBOARD_OPERATOR_GROUP_ID": "dashboard ACA App definition from Entra config",
    "EVAL_MAX_RMSE": "evaluation ACA Job default; evaluate.py defaults locally",
    # LLM release-artifact secrets; Key Vault-backed in production.
    "MODEL_API_KEY": "Key Vault secret, injected into the LLM evaluation job",
    "MODEL_API_KEY_SECRET": "Key Vault secret name, set by the job definition",
    "KEY_VAULT_URL": "job definition pointing at the platform Key Vault",
    # Dormant broker upgrade path; absent from the baseline deployment.
    "REDIS_URL": "managed Redis connection, set when the broker module is deployed",
    # Distributed-training runtime variables (chapter 14 exception path).
    "LOCAL_RANK": "torch distributed launcher, injected at process start",
    "OMPI_COMM_WORLD_LOCAL_RANK": "OpenMPI launcher, injected at process start",
    # Per-execution correlation id, injected at runtime rather than statically:
    # the local runner exports it before starting a job, and the dashboard's
    # ACA trigger template sets it on production executions.
    "RESULTS_RUN_ID": "runner / dashboard trigger template, per execution",
}

_ENV_LITERAL_RES = (
    re.compile(r"""os\.environ\.get\(\s*['"]([A-Z_][A-Z0-9_]*)['"]"""),
    re.compile(r"""os\.environ\[\s*['"]([A-Z_][A-Z0-9_]*)['"]\s*\]"""),
)
# os.environ.get(SOME_CONST): resolve via a module-level string assignment.
_ENV_CONST_ARG_RE = re.compile(r"os\.environ\.get\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*[,)]")

_SERVICE_RE = re.compile(r"^ {2}([\w-]+):\s*$")
_ENV_BLOCK_RE = re.compile(r"^( +)environment:(?:\s+&([\w-]+))?\s*$")
_ENTRY_RE = re.compile(r"^ +([A-Za-z_][A-Za-z0-9_]*)\s*:")
_MERGE_RE = re.compile(r"^ +<<\s*:\s*\*([\w-]+)\s*$")


def _env_keys_in_file(text: str) -> set[str]:
    keys: set[str] = set()
    for pattern in _ENV_LITERAL_RES:
        keys.update(pattern.findall(text))
    for const_name in _ENV_CONST_ARG_RE.findall(text):
        match = re.search(
            rf"^{re.escape(const_name)}\s*(?::\s*str)?\s*=\s*['\"]([A-Z_][A-Z0-9_]*)['\"]",
            text,
            re.MULTILINE,
        )
        if match:
            keys.add(match.group(1))
    return keys


def _consumed_vars(src_dir: Path) -> dict[str, set[str]]:
    """Map env var -> set of src-relative files that read it."""
    consumers: dict[str, set[str]] = defaultdict(set)
    for path in sorted(src_dir.rglob("*.py")):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        for key in _env_keys_in_file(path.read_text(encoding="utf-8")):
            consumers[key].add(rel)
    return dict(consumers)


def _compose_provided(compose_path: Path) -> dict[str, set[str]]:
    """Map env var -> set of services whose environment block provides it."""
    provided: dict[str, set[str]] = defaultdict(set)
    anchors: dict[str, set[str]] = {}
    service = ""
    block_indent = -1
    active_anchor = ""

    for raw_line in compose_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip())

        if block_indent != -1 and indent <= block_indent:
            block_indent = -1  # dedent closes the environment block
            active_anchor = ""
        if indent == 0:
            continue

        if block_indent == -1:
            service_match = _SERVICE_RE.match(raw_line)
            if service_match:
                service = service_match.group(1)
                continue
            block_match = _ENV_BLOCK_RE.match(raw_line)
            if block_match and service:
                block_indent = indent
                active_anchor = block_match.group(2) or ""
                if active_anchor and active_anchor not in anchors:
                    anchors[active_anchor] = set()
                continue
            continue

        merge_match = _MERGE_RE.match(raw_line)
        if merge_match:
            for key in anchors.get(merge_match.group(1), ()):
                provided[key].add(service)
            continue
        entry_match = _ENTRY_RE.match(raw_line)
        if entry_match:
            key = entry_match.group(1)
            provided[key].add(service)
            if active_anchor:
                anchors[active_anchor].add(key)

    return dict(provided)


def _print_table(title: str, headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> None:
    print(f"{title}:")
    if not rows:
        print("  (none)\n")
        return
    widths = [
        max(len(header), *(len(row[column]) for row in rows))
        for column, header in enumerate(headers)
    ]
    ruler = "  ".join(header.ljust(width) for header, width in zip(headers, widths, strict=True))
    print(f"  {ruler}")
    print(f"  {'-' * len(ruler)}")
    for row in rows:
        cells = (cell.ljust(width) for cell, width in zip(row, widths, strict=True))
        print(f"  {'  '.join(cells).rstrip()}")
    print()


def main() -> int:
    consumed = _consumed_vars(SRC_DIR)
    provided = _compose_provided(COMPOSE_FILE)

    def files_of(files: set[str]) -> str:
        return ", ".join(sorted(files))

    given_rows = [
        (var, files_of(files), ", ".join(sorted(provided[var])))
        for var, files in sorted(consumed.items())
        if var in provided
    ]
    allowed_rows = [
        (var, files_of(files), ALLOWED_MISSING[var])
        for var, files in sorted(consumed.items())
        if var in ALLOWED_MISSING
    ]
    missing_rows = [
        (var, files_of(files))
        for var, files in sorted(consumed.items())
        if var not in provided and var not in ALLOWED_MISSING
    ]

    print("Environment contract: src/ consumers vs demo/docker-compose.yml\n")
    _print_table(
        "Provided by compose",
        ("VAR", "CONSUMED BY", "COMPOSE SERVICES"),
        given_rows,
    )
    _print_table(
        "Allow-listed (injected outside compose)",
        ("VAR", "CONSUMED BY", "INJECTED BY"),
        allowed_rows,
    )
    _print_table("MISSING from compose", ("VAR", "CONSUMED BY"), missing_rows)

    if missing_rows:
        print(f"FAIL: {len(missing_rows)} consumed variable(s) missing from the Compose demo")
        return 1
    print("OK: every variable consumed under src/ is provided by compose or allow-listed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
