# Training / evaluation ACA Job image (docs/02).
# Pinned base + deps + the ml_platform package. The image digest is what makes a
# run reproducible, so builds are content-addressed and referenced by digest.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first for layer caching.
COPY src/train_job/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# The shared platform package (common/ helpers) and the job entrypoints.
COPY src/ml_platform ./ml_platform
COPY src/train_job/train.py src/train_job/evaluate.py src/train_job/register_llm.py ./

# Default to training; the eval Job overrides the command to `evaluate.py`.
ENTRYPOINT ["python", "train.py"]
