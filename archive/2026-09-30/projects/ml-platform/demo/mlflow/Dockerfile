FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY demo/mlflow/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY demo/mlflow/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 5000
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=20 \
    CMD curl -fsS http://localhost:5000/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
