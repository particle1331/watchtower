#!/usr/bin/env bash
###############################################################################
# Start the self-hosted MLflow server against Postgres (Entra auth) + Blob.
#
# No passwords: we fetch an Entra access token for Postgres using the id-mlflow
# managed identity (selected by AZURE_CLIENT_ID) and pass it as the libpq
# password. Blob artifact access uses the same identity via DefaultAzureCredential
# inside MLflow's azure-storage-blob backend.
#
# Token lifetime note: the Postgres access token is valid ~24h. New DB
# connections after expiry need a fresh token; for the MVP the App is restarted
# on a schedule (or a pgbouncer/token-refresh sidecar is added in hardening).
###############################################################################
set -euo pipefail

: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGDATABASE:=mlflow}"
: "${MLFLOW_HOST:=0.0.0.0}"
: "${MLFLOW_PORT:=5000}"
: "${MLFLOW_ARTIFACTS_DESTINATION:?MLFLOW_ARTIFACTS_DESTINATION is required}"

echo "Acquiring Postgres access token via managed identity (${AZURE_CLIENT_ID:-default})..."
PGTOKEN="$(python - <<'PY'
from azure.identity import DefaultAzureCredential
cred = DefaultAzureCredential()
# The OSS RDBMS scope yields a token that is used as the Postgres password.
print(cred.get_token("https://ossrdbms-aad.database.windows.net/.default").token)
PY
)"

# JWTs are URL-safe (base64url + dots), so they are safe in the password slot.
export MLFLOW_BACKEND_STORE_URI="postgresql+psycopg2://${PGUSER}:${PGTOKEN}@${PGHOST}:5432/${PGDATABASE}?sslmode=require"

# MLflow 3 adds database migrations for the tracking and registry schema. The
# command is idempotent on a current schema and makes an image upgrade safe for
# an existing MLflow database. Set MLFLOW_DB_UPGRADE=false when migrations are
# run separately as part of a controlled deployment.
if [[ "${MLFLOW_DB_UPGRADE:-true}" == "true" ]]; then
  echo "Upgrading MLflow database schema..."
  mlflow db upgrade "${MLFLOW_BACKEND_STORE_URI}"
fi

echo "Starting MLflow on ${MLFLOW_HOST}:${MLFLOW_PORT} (backend=postgres/${PGDATABASE}, artifacts=${MLFLOW_ARTIFACTS_DESTINATION})"
exec mlflow server \
  --host "${MLFLOW_HOST}" \
  --port "${MLFLOW_PORT}" \
  --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
  --artifacts-destination "${MLFLOW_ARTIFACTS_DESTINATION}" \
  --allowed-hosts "${MLFLOW_ALLOWED_HOSTS:-*}" \
  --serve-artifacts
