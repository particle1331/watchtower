FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY demo/runner/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ml_platform ./ml_platform
COPY src/train_job/train.py ./train.py
COPY src/train_job/evaluate.py ./evaluate.py
COPY src/batch_job/score.py ./score.py
COPY demo/runner/app.py ./app.py

EXPOSE 8090
ENTRYPOINT ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]
