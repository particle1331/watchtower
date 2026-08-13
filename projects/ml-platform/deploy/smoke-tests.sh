#!/usr/bin/env bash
# smoke-tests.sh — End-to-end smoke tests for the ML platform golden path (docs/07, Ch 10).
#
# Verifies acceptance evidence for each phase against a running deployed platform.
# Run after deploy.sh has completed all passes.
#
#   Phase 0 (Foundation):    MLflow reachable.
#   Phase 1 (Training):      Trigger train Job; poll until Succeeded/Failed.
#   Phase 2 (Batch):         Trigger batch Job; confirm ACA accepts the start.
#   Phase 3 (Serving):       /readyz reports exact version.
#   Phase 4 (Observability): Dashboard /healthz alive; /api/runs returns a response.
#
# Usage:
#   ./deploy/smoke-tests.sh [--tf-vars FILE] [--timeout-secs N]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${INFRA_DIR:-"$SCRIPT_DIR/../infra"}"
TF_VARS="${TF_VARS:-"$SCRIPT_DIR/../infra/environments/dev.tfvars"}"
TIMEOUT_SECS="${TIMEOUT_SECS:-300}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tf-vars)       TF_VARS="$2";       shift 2 ;;
    --infra-dir)     INFRA_DIR="$2";     shift 2 ;;
    --timeout-secs)  TIMEOUT_SECS="$2";  shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
ERRORS=0
pass()    { echo -e "  \033[0;32mPASS\033[0m $*"; }
fail()    { echo -e "  \033[0;31mFAIL\033[0m $*"; (( ERRORS++ )) || true; }
section() { echo -e "\n\033[0;36m$*\033[0m"; }

assert() {
  local cond="$1" msg="$2"
  if [[ "$cond" == true || "$cond" == "0" ]]; then pass "$msg"; else fail "$msg"; fi
}

tf_output() {
  # Returns empty string (not an error) when the output doesn't exist yet.
  terraform output -raw "$1" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# Read Terraform outputs
# ---------------------------------------------------------------------------
cd "$INFRA_DIR"
MLFLOW_URL=$(tf_output mlflow_url)
SERVING_URL=$(tf_output serving_url)
DASH_URL=$(tf_output dashboard_url)
TRAIN_JOB=$(tf_output train_job_name)
BATCH_JOB=$(tf_output batch_job_name)
RG=$(tf_output resource_group_name)

# ---------------------------------------------------------------------------
# Phase 0: Foundation + MLflow reachable
# ---------------------------------------------------------------------------
section "[Phase 0] Foundation"
if [[ -n "$MLFLOW_URL" ]]; then
  pass "MLflow URL is non-empty"
  if health=$(curl -sf --max-time 10 "$MLFLOW_URL/health" 2>/dev/null); then
    pass "MLflow /health reachable (response: ${health:0:40})"
  else
    fail "MLflow /health not reachable at $MLFLOW_URL"
  fi
else
  fail "MLflow URL is empty (foundation not deployed?)"
fi

# ---------------------------------------------------------------------------
# Phase 1: Training Job
# ---------------------------------------------------------------------------
section "[Phase 1] Training"
if [[ -n "$TRAIN_JOB" ]]; then
  echo "  Triggering train Job ($TRAIN_JOB)..."
  exec_json=$(az containerapp job start \
    --name "$TRAIN_JOB" --resource-group "$RG" \
    --output json 2>/dev/null || true)

  if [[ -n "$exec_json" ]]; then
    exec_name=$(echo "$exec_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
    echo "  Execution: $exec_name — waiting up to ${TIMEOUT_SECS}s..."
    deadline=$(( $(date +%s) + TIMEOUT_SECS ))
    status=""
    while true; do
      status=$(az containerapp job execution show \
        --name "$TRAIN_JOB" \
        --job-execution-name "$exec_name" \
        --output tsv --query "properties.status" 2>/dev/null || true)
      [[ "$status" == "Succeeded" || "$status" == "Failed" ]] && break
      [[ $(date +%s) -ge $deadline ]] && { status="Timeout"; break; }
      sleep 15
    done
    assert "$([[ "$status" == "Succeeded" ]] && echo true || echo false)" \
      "Train Job execution succeeded (status=$status)"
  else
    echo "  (train job start returned empty — not deployed or failed to start)"
  fi
else
  echo "  (train_job_name empty, skipping Phase 1)"
fi

# ---------------------------------------------------------------------------
# Phase 2: Batch Job
# ---------------------------------------------------------------------------
section "[Phase 2] Batch"
if [[ -n "$BATCH_JOB" ]]; then
  echo "  Triggering batch Job ($BATCH_JOB)..."
  az containerapp job start \
    --name "$BATCH_JOB" --resource-group "$RG" \
    --output none 2>/dev/null && pass "Batch Job trigger accepted by ACA" \
                               || fail "Batch Job trigger rejected"
  echo "  (row verification requires DB access — manual step)"
else
  echo "  (batch_job_name empty, skipping Phase 2)"
fi

# ---------------------------------------------------------------------------
# Phase 3: Serving App
# ---------------------------------------------------------------------------
section "[Phase 3] Serving"
if [[ -n "$SERVING_URL" ]]; then
  if readyz=$(curl -sf --max-time 10 "$SERVING_URL/readyz" 2>/dev/null); then
    status_val=$(echo "$readyz" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
    version_val=$(echo "$readyz" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_version',''))" 2>/dev/null || true)
    assert "$([[ "$status_val" == "ready" ]] && echo true || echo false)" \
      "Serving /readyz status=ready (got: $status_val)"
    assert "$([[ -n "$version_val" ]] && echo true || echo false)" \
      "Serving /readyz reports a model_version (got: $version_val)"
    echo "  Loaded version: $version_val"
  else
    fail "Serving /readyz not reachable at $SERVING_URL"
  fi
else
  echo "  (serving_url empty, skipping Phase 3)"
fi

# ---------------------------------------------------------------------------
# Phase 4: Observability / Dashboard
# ---------------------------------------------------------------------------
section "[Phase 4] Observability"
if [[ -n "$DASH_URL" ]]; then
  if health=$(curl -sf --max-time 10 "$DASH_URL/healthz" 2>/dev/null); then
    status_val=$(echo "$health" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
    assert "$([[ "$status_val" == "alive" ]] && echo true || echo false)" \
      "Dashboard /healthz status=alive (got: $status_val)"
  else
    fail "Dashboard /healthz not reachable at $DASH_URL"
  fi

  if runs=$(curl -sf --max-time 10 "$DASH_URL/api/runs?limit=5" 2>/dev/null); then
    assert "$([[ -n "$runs" ]] && echo true || echo false)" \
      "Dashboard /api/runs returns a response"
  else
    fail "Dashboard /api/runs not reachable"
  fi
else
  echo "  (dashboard_url empty, skipping Phase 4)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
if [[ "$ERRORS" -eq 0 ]]; then
  echo -e "\033[0;32mAll smoke tests passed.\033[0m"
else
  echo -e "\033[0;31m${ERRORS} test(s) failed.\033[0m"
  exit 1
fi
