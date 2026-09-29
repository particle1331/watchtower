# Batch scoring ACA Job image.
# Mirrors the train_job image structure: pinned base, deps layer, then sources.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for layer caching.
COPY src/batch_job/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# The shared platform package (results store, MLflow helpers) and the job entrypoint.
COPY src/ml_platform ./ml_platform
COPY src/batch_job/score.py ./

ENTRYPOINT ["python", "score.py"]
