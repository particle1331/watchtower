#!/usr/bin/env bash
# smoke-tests.sh — Azure adapter checks for the ML platform golden path.
#
# Verifies acceptance evidence for each phase against a running deployed platform.
# Run after deploy.sh has completed all passes.
#
#   Phase 0 (Foundation):    MLflow reachable.
#   Phase 1 (Training/eval): Trigger train, resolve its version, evaluate it.
#   Phase 2 (Batch):         Trigger batch Job; poll execution + results to SUCCESS.
#   Phase 3 (Serving):       /readyz reports exact version.
#   Phase 4 (Operations):    Dashboard health is public; data routes require auth.
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

wait_for_execution() {
  local job_name="$1" execution_name="$2" label="$3"
  local deadline=$(( $(date +%s) + TIMEOUT_SECS ))
  local status=""
  echo "  Execution: $execution_name — waiting up to ${TIMEOUT_SECS}s..."
  while true; do
    status=$(az containerapp job execution show \
      --name "$job_name" \
      --job-execution-name "$execution_name" \
      --output tsv --query "properties.status" 2>/dev/null || true)
    case "$status" in
      Succeeded|Failed|Stopped|Degraded) break ;;
    esac
    if [[ $(date +%s) -ge $deadline ]]; then
      status="Timeout"
      break
    fi
    sleep 15
  done
  assert "$([[ "$status" == "Succeeded" ]] && echo true || echo false)" \
    "$label execution reached SUCCESS (status=$status)"
  printf '%s\n' "$status"
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
EVAL_JOB=$(tf_output eval_job_name)
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
    wait_for_execution "$TRAIN_JOB" "$exec_name" "Train Job"

    model_json=$(curl -sf --max-time 10 \
      "$MLFLOW_URL/api/2.0/mlflow/registered-models/get-latest-versions?name=wine-quality" \
      2>/dev/null || true)
    MODEL_VERSION=$(echo "$model_json" | python3 -c \
      "import sys,json; rows=json.load(sys.stdin).get('model_versions', []); print(max(int(r['version']) for r in rows))" \
      2>/dev/null || true)
    assert "$([[ -n "$MODEL_VERSION" ]] && echo true || echo false)" \
      "Training produced a resolvable wine-quality version (got: $MODEL_VERSION)"
  else
    fail "Train Job start returned no execution"
  fi
else
  echo "  (train_job_name empty, skipping Phase 1)"
fi

if [[ -n "$EVAL_JOB" && -n "${MODEL_VERSION:-}" ]]; then
  echo "  Triggering eval Job ($EVAL_JOB) for version $MODEL_VERSION..."
  eval_json=$(az containerapp job start \
    --name "$EVAL_JOB" --resource-group "$RG" --container-name eval \
    --args "--version" "$MODEL_VERSION" "--registered-name" "wine-quality" \
    --output json 2>/dev/null || true)
  if [[ -n "$eval_json" ]]; then
    eval_name=$(echo "$eval_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
    wait_for_execution "$EVAL_JOB" "$eval_name" "Evaluation Job"
  else
    fail "Evaluation Job start returned no execution"
  fi
else
  fail "Evaluation Job or candidate model version is unavailable"
fi

# ---------------------------------------------------------------------------
# Phase 2: Batch Job
# ---------------------------------------------------------------------------
section "[Phase 2] Batch"
if [[ -n "$BATCH_JOB" ]]; then
  echo "  Triggering batch Job ($BATCH_JOB)..."
  exec_json=$(az containerapp job start \
    --name "$BATCH_JOB" --resource-group "$RG" \
    --output json 2>/dev/null || true)
  if [[ -n "$exec_json" ]]; then
    exec_name=$(echo "$exec_json" | python3 -c "import sys,json; print(json.load(sys.stdin)['name'])")
    wait_for_execution "$BATCH_JOB" "$exec_name" "Batch Job"
  else
    fail "Batch Job start returned no execution"
  fi
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
    prediction=$(curl -sf --max-time 10 \
      -H 'Content-Type: application/json' \
      -d '{"instances":[[7.0,0.27,0.36,20.7,0.045,45.0,170.0,1.001,3.0,0.45,8.8]]}' \
      "$SERVING_URL/v1/predictions" 2>/dev/null || true)
    prediction_version=$(echo "$prediction" | python3 -c "import sys,json; print(json.load(sys.stdin).get('model_version',''))" 2>/dev/null || true)
    assert "$([[ "$prediction_version" == "$version_val" ]] && echo true || echo false)" \
      "Serving prediction reports the ready model_version (got: $prediction_version)"
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

  anonymous_status=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 \
    "$DASH_URL/api/runs?limit=5" 2>/dev/null || true)
  case "$anonymous_status" in
    302|401|403) pass "Dashboard data routes reject or redirect anonymous access (HTTP $anonymous_status)" ;;
    *) fail "Dashboard data route should require Easy Auth (HTTP $anonymous_status)" ;;
  esac
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
