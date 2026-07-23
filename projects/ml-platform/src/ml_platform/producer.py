"""Demo task producer.

Publishes synthetic documents to the Celery task queue via Redis.

Usage:
    make producer
    uv run python -m ml_platform.producer
"""

import logging

from ml_platform.tasks import RELEASE_ID, TASK_CONTRACT_VERSION, process_document

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEMO_DOCS = [
    "The quick brown fox jumps over the lazy dog near the riverbank.",
    "Machine learning models require careful feature engineering and validation.",
    "Idempotency ensures that duplicate deliveries do not cause duplicate side effects.",
    "Redis provides atomic SETNX operations for distributed locking patterns.",
    "Celery workers scale horizontally with KEDA based on Redis list length.",
    "Azure Container Apps run serverless containers with automatic HTTPS ingress.",
    "Bicep is a domain-specific language for declarative Azure resource deployment.",
    "MLflow tracks experiments, registers models, and manages prompt versions.",
    "PostgreSQL serves as the durable metadata backend for MLflow tracking.",
    "Application Insights captures structured telemetry with correlation ids.",
]


def main() -> None:
    logger.info("Publishing %d demo documents to Celery", len(DEMO_DOCS))

    tasks = []
    for i, content in enumerate(DEMO_DOCS):
        task = process_document.delay(
            doc_id=f"demo-{i:03d}",
            doc_content=content,
            model_version="1",
            prompt_version="1",
            contract_version=TASK_CONTRACT_VERSION,
            release_id=RELEASE_ID,
        )
        tasks.append(task)
        logger.info("Published: doc=demo-%03d task=%s", i, task.id)

    logger.info("Waiting for results...")
    for i, task in enumerate(tasks):
        result = task.get(timeout=30)
        logger.info("Result demo-%03d: %s", i, result)

    logger.info("All %d tasks complete", len(tasks))


if __name__ == "__main__":
    main()
