#!/usr/bin/env sh
set -eu

: "${PGHOST:?PGHOST is required}"
: "${PGUSER:?PGUSER is required}"
: "${PGPASSWORD:?PGPASSWORD is required}"
: "${PGDATABASE:=mlflow}"
: "${MLFLOW_HOST:=0.0.0.0}"
: "${MLFLOW_PORT:=5000}"
: "${MLFLOW_ARTIFACTS_DESTINATION:?MLFLOW_ARTIFACTS_DESTINATION is required}"

export MLFLOW_BACKEND_STORE_URI="postgresql+psycopg2://${PGUSER}:${PGPASSWORD}@${PGHOST}:${PGPORT:-5432}/${PGDATABASE}?sslmode=${PGSSLMODE:-disable}"

# MLflow 3 may require a backend-store migration when reusing a v2 database.
# This demo database is disposable, and the command is idempotent on restart.
mlflow db upgrade "${MLFLOW_BACKEND_STORE_URI}"

exec mlflow server \
  --host "${MLFLOW_HOST}" \
  --port "${MLFLOW_PORT}" \
  --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
  --artifacts-destination "${MLFLOW_ARTIFACTS_DESTINATION}" \
  --allowed-hosts "${MLFLOW_ALLOWED_HOSTS:-*}" \
  --serve-artifacts
