#!/usr/bin/env bash
# deploy.sh — Full platform deploy: foundation, workloads, and observability.
#
# Multi-pass deploy that brings up the whole platform incrementally:
#   1. terraform apply — foundation only (ACR, Postgres, storage, identities)
#   2. Build + push MLflow image; run grants.sql + schema.sql; apply MLflow pass
#   3. Build + push train/batch/serving/dashboard images
#   4. terraform apply — all images pinned; full platform running
#   5. (Optional) run smoke-tests.sh to verify acceptance evidence
#
# Images with empty vars skip the corresponding module (two-pass gating).
# Auth is managed-identity / Entra throughout; no passwords in this script.
# Requires: az CLI (logged in), terraform >= 1.6, psql, Docker (or az acr build).
#
# Usage:
#   ./deploy/deploy.sh --pg-admin-upn you@example.com [options]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${INFRA_DIR:-"$SCRIPT_DIR/../infra"}"
TF_VARS="${TF_VARS:-"$SCRIPT_DIR/../infra/environments/dev.tfvars"}"
MLFLOW_IMAGE_REPO="${MLFLOW_IMAGE_REPO:-mlflow-app}"
TRAIN_IMAGE_REPO="${TRAIN_IMAGE_REPO:-train-job}"
BATCH_IMAGE_REPO="${BATCH_IMAGE_REPO:-batch-job}"
SERVING_IMAGE_REPO="${SERVING_IMAGE_REPO:-serving-app}"
DASH_IMAGE_REPO="${DASH_IMAGE_REPO:-dashboard}"
SERVING_MODEL_NAME="${SERVING_MODEL_NAME:-wine-quality}"
SERVING_MODEL_VERSION="${SERVING_MODEL_VERSION:-}"
LLM_EVAL_DATASET="${LLM_EVAL_DATASET:-}"
LLM_MODEL_NAME="${LLM_MODEL_NAME:-llm-app}"
LLM_MODEL_VERSION="${LLM_MODEL_VERSION:-1}"
SKIP_SMOKE_TESTS="${SKIP_SMOKE_TESTS:-false}"
PG_ADMIN_UPN=""

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
usage() {
  echo "Usage: $0 --pg-admin-upn UPN [--tf-vars FILE] [--serving-model-version N] [--skip-smoke-tests]"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pg-admin-upn)           PG_ADMIN_UPN="$2";           shift 2 ;;
    --tf-vars)                TF_VARS="$2";                 shift 2 ;;
    --infra-dir)              INFRA_DIR="$2";               shift 2 ;;
    --serving-model-version)  SERVING_MODEL_VERSION="$2";  shift 2 ;;
    --serving-model-name)     SERVING_MODEL_NAME="$2";     shift 2 ;;
    --skip-smoke-tests)       SKIP_SMOKE_TESTS=true;        shift   ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

[[ -z "$PG_ADMIN_UPN" ]] && { echo "ERROR: --pg-admin-upn is required"; usage; }

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()    { echo -e "\033[0;36m==> $*\033[0m"; }
success() { echo -e "\033[0;32m    $*\033[0m"; }

build_and_push() {
  local acr_name="$1" acr_login="$2" repo="$3" src_dir="$4"
  local tag="$repo:latest"
  # Redirect all diagnostic output to stderr so the caller captures only the
  # final pinned image reference on stdout.
  echo "    building $tag from $src_dir" >&2
  az acr build --registry "$acr_name" --image "$tag" "$src_dir" >&2
  local digest
  digest=$(az acr repository show --name "$acr_name" --image "$tag" --query "digest" -o tsv)
  echo "${acr_login}/${repo}@${digest}"
}

# ---------------------------------------------------------------------------
# Pass 1: foundation only
# ---------------------------------------------------------------------------
info "[1/4] terraform init + foundation apply"
cd "$INFRA_DIR"
terraform init -input=false
terraform apply -input=false -auto-approve -var-file "$TF_VARS" \
  -var 'mlflow_image=' -var 'train_image=' -var 'batch_image=' \
  -var 'serving_image=' -var 'dashboard_image=' -var 'llm_image='

ACR_NAME=$(terraform output -raw acr_name)
ACR_LOGIN=$(terraform output -raw acr_login_server)
PG_FQDN=$(terraform output -raw postgres_fqdn)

# ---------------------------------------------------------------------------
# Pass 2: MLflow image + DB setup
# ---------------------------------------------------------------------------
info "[2/4] build + push MLflow image; run grants.sql + schema.sql"
MLFLOW_IMAGE=$(build_and_push "$ACR_NAME" "$ACR_LOGIN" "$MLFLOW_IMAGE_REPO" "$SCRIPT_DIR/../src/mlflow_app")
success "MLflow pinned: $MLFLOW_IMAGE"

PG_TOKEN=$(az account get-access-token --resource-type oss-rdbms --query accessToken -o tsv)
export PGPASSWORD="$PG_TOKEN"

OID_TRAIN=$(terraform output -json identity_principal_ids | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id-jobs-train'])")
OID_BATCH=$(terraform output -json identity_principal_ids | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id-jobs-batch'])")
OID_MLFLOW=$(terraform output -json identity_principal_ids | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id-mlflow'])")
OID_DASH=$(terraform output -json identity_principal_ids | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['id-dashboard'])")

# grants.sql — Postgres principals + schema privileges. It runs once before
# schema.sql so the workload principals exist, then again below so grants on
# newly-created results tables are applied.
psql "host=$PG_FQDN port=5432 dbname=postgres user=$PG_ADMIN_UPN sslmode=require" \
  -v oid_jobs_train="$OID_TRAIN" \
  -v oid_jobs_batch="$OID_BATCH" \
  -v oid_mlflow="$OID_MLFLOW" \
  -v oid_dashboard="$OID_DASH" \
  -f grants.sql

# schema.sql — results table DDL (idempotent IF NOT EXISTS)
SCHEMA_PATH="$SCRIPT_DIR/../src/ml_platform/results/schema.sql"
if [[ -f "$SCHEMA_PATH" ]]; then
  psql "host=$PG_FQDN port=5432 dbname=results user=$PG_ADMIN_UPN sslmode=require" -f "$SCHEMA_PATH"
  psql "host=$PG_FQDN port=5432 dbname=postgres user=$PG_ADMIN_UPN sslmode=require" \
    -v oid_jobs_train="$OID_TRAIN" \
    -v oid_jobs_batch="$OID_BATCH" \
    -v oid_mlflow="$OID_MLFLOW" \
    -v oid_dashboard="$OID_DASH" \
    -f grants.sql
fi
unset PGPASSWORD

# Apply with MLflow image so the App goes live.
terraform apply -input=false -auto-approve -var-file "$TF_VARS" \
  -var "mlflow_image=$MLFLOW_IMAGE" -var 'train_image=' -var 'batch_image=' \
  -var 'serving_image=' -var 'dashboard_image=' -var 'llm_image='

# ---------------------------------------------------------------------------
# Pass 3: build remaining images
# ---------------------------------------------------------------------------
info "[3/4] build + push train / batch / serving / dashboard images"
TRAIN_IMAGE=$(build_and_push   "$ACR_NAME" "$ACR_LOGIN" "$TRAIN_IMAGE_REPO"   "$SCRIPT_DIR/..")
BATCH_IMAGE=$(build_and_push   "$ACR_NAME" "$ACR_LOGIN" "$BATCH_IMAGE_REPO"   "$SCRIPT_DIR/..")
SERVING_IMAGE=$(build_and_push "$ACR_NAME" "$ACR_LOGIN" "$SERVING_IMAGE_REPO" "$SCRIPT_DIR/..")
DASH_IMAGE=$(build_and_push    "$ACR_NAME" "$ACR_LOGIN" "$DASH_IMAGE_REPO"    "$SCRIPT_DIR/..")
success "train:   $TRAIN_IMAGE"
success "batch:   $BATCH_IMAGE"
success "serving: $SERVING_IMAGE"
success "dash:    $DASH_IMAGE"

# ---------------------------------------------------------------------------
# Pass 4: apply with all images pinned
# ---------------------------------------------------------------------------
info "[4/4] terraform apply — full platform"
SERV_VARS=()
if [[ -n "$SERVING_MODEL_VERSION" ]]; then
  SERV_VARS=(
    -var "serving_model_version=$SERVING_MODEL_VERSION"
    -var "serving_model_name=$SERVING_MODEL_NAME"
  )
fi

terraform apply -input=false -auto-approve -var-file "$TF_VARS" \
  -var "mlflow_image=$MLFLOW_IMAGE" \
  -var "train_image=$TRAIN_IMAGE" \
  -var "batch_image=$BATCH_IMAGE" \
  -var "serving_image=$SERVING_IMAGE" \
  -var "dashboard_image=$DASH_IMAGE" \
  -var "llm_image=$TRAIN_IMAGE" \
  -var "llm_eval_dataset=$LLM_EVAL_DATASET" \
  -var "llm_model_name=$LLM_MODEL_NAME" \
  -var "llm_model_version=$LLM_MODEL_VERSION" \
  "${SERV_VARS[@]+"${SERV_VARS[@]}"}"

echo ""
success "Done. Endpoints:"
terraform output

# ---------------------------------------------------------------------------
# Optional smoke tests
# ---------------------------------------------------------------------------
if [[ "$SKIP_SMOKE_TESTS" != true ]]; then
  info "Running smoke tests..."
  "$SCRIPT_DIR/smoke-tests.sh" --tf-vars "$TF_VARS"
fi
