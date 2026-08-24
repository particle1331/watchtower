# Serving ACA App image.
# Own image: we control framework, runtime, and dependencies (no framework lock-in).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY src/serving_app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/serving_app/app.py ./app.py

EXPOSE 8080

# Liveness check — /healthz is always up once the process runs.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=5 \
    CMD curl -fsS http://localhost:${PORT:-8080}/healthz || exit 1

ENTRYPOINT ["python", "app.py"]
