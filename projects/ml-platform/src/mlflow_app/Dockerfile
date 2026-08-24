# Self-hosted MLflow tracking + registry server.
#
# Pinned MLflow and driver versions let us control the exact version instead of
# inheriting Azure ML's managed version. Postgres metadata backend + Blob artifact store, both
# reached with the id-mlflow managed identity (no passwords). Pin the base image
# by digest in real builds; a tag is shown here for readability.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# psql client is used at container start to acquire nothing — auth tokens are
# fetched via azure-identity; curl is kept only for health debugging.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 5000

# Basic container healthcheck against MLflow's health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS "http://localhost:${MLFLOW_PORT:-5000}/health" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
