"""Celery application and configuration.

Key decisions:
- acks_late=True          — acknowledge only after task completes (not on dequeue)
- task_reject_on_worker_lost=True — redeliver immediately if worker crashes
- worker_prefetch_multiplier=1    — one task per worker at a time (predictable scaling)
- result_expires=604800          — 7-day result TTL (aligned with idempotency window)
- broker_transport_options with visibility_timeout — Redis visibility timeout
"""

from celery import Celery

REDIS_URL = "redis://localhost:6379/0"

app = Celery("ml_platform")

app.conf.update(
    broker_url=REDIS_URL,
    result_backend=REDIS_URL,
    result_expires=604800,  # 7 days
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_transport_options={
        "visibility_timeout": 3600,  # 1 hour — tasks must complete within this
    },
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_soft_time_limit=300,   # 5-minute warning
    task_time_limit=600,        # 10-minute hard kill
)

# Beat schedule for reconciliation producer
app.conf.beat_schedule = {
    "reconcile-every-5-minutes": {
        "task": "ml_platform.tasks.reconcile_documents",
        "schedule": 300.0,  # seconds
    },
}

# Import tasks so Celery discovers them
import ml_platform.tasks  # noqa: E402, F401
