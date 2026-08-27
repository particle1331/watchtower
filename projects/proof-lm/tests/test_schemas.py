from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from proof_lm.benchmark import reference_bundle
from proof_lm.schemas import (
    EXPERIMENT_SCHEMA,
    REPORT_SCHEMA,
    ArtifactIdentityError,
    ArtifactRef,
    EvaluatorReport,
    ExperimentRecord,
    validate_evaluation_bundle,
)


def make_report(**changes) -> EvaluatorReport:
    checkpoint, tokenizer, dataset = reference_bundle()
    values = {
        "schema_version": REPORT_SCHEMA,
        "report_id": "report-v1",
        "checkpoint_id": checkpoint.checkpoint_id,
        "tokenizer_id": tokenizer.tokenizer_id,
        "dataset_manifest_id": dataset.dataset_manifest_id,
        "evaluator_id": "evaluator-v1",
        "evaluator_version": "1",
        "decoding_config_id": "greedy-v1",
        "seed": 17,
        "suites": {"proof": {"validity": 1.0}},
        "accepted": True,
    }
    values.update(changes)
    return EvaluatorReport(**values)


def test_checkpoint_and_report_carry_the_complete_lineage() -> None:
    checkpoint, tokenizer, dataset = reference_bundle()
    assert checkpoint.state.model
    assert checkpoint.state.optimizer
    assert checkpoint.state.scheduler
    assert checkpoint.state.data_cursor
    assert checkpoint.state.rng_state
    report = make_report()
    validate_evaluation_bundle(report, checkpoint, tokenizer, dataset, "evaluator-v1", "1")


def test_checkpoint_tokenizer_identity_is_checked_independently() -> None:
    checkpoint, tokenizer, dataset = reference_bundle()
    mismatched_checkpoint = checkpoint.model_copy(update={"tokenizer_id": "wrong-tokenizer"})
    with pytest.raises(ArtifactIdentityError, match="tokenizer/checkpoint"):
        validate_evaluation_bundle(
            make_report(), mismatched_checkpoint, tokenizer, dataset, "evaluator-v1", "1"
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("checkpoint_id", "wrong-checkpoint"),
        ("tokenizer_id", "wrong-tokenizer"),
        ("dataset_manifest_id", "wrong-dataset"),
        ("evaluator_id", "wrong-evaluator"),
        ("evaluator_version", "wrong-version"),
    ],
)
def test_evaluation_rejects_incompatible_identity(field: str, value: str) -> None:
    checkpoint, tokenizer, dataset = reference_bundle()
    report = make_report(**{field: value})
    with pytest.raises(ArtifactIdentityError):
        validate_evaluation_bundle(report, checkpoint, tokenizer, dataset, "evaluator-v1", "1")


def test_experiment_record_requires_completion_for_success() -> None:
    with pytest.raises(ValidationError, match="completed_at"):
        ExperimentRecord(
            schema_version=EXPERIMENT_SCHEMA,
            run_id="run-v1",
            stage="contract",
            profile="smoke",
            config_id="cfg-v1",
            inputs={"dataset": ArtifactRef(kind="dataset", artifact_id="dataset-v1")},
            outputs={},
            seed=17,
            status="succeeded",
            started_at=datetime.now(UTC),
            processed_tokens=0,
            processed_examples=0,
            optimizer_updates=0,
            device="cpu",
            software={"python": "3.14"},
            wall_time_seconds=0,
            peak_memory_bytes=0,
            cost_usd=0,
        )


def test_experiment_record_serializes_timestamps_and_artifact_refs() -> None:
    now = datetime.now(UTC)
    record = ExperimentRecord(
        schema_version=EXPERIMENT_SCHEMA,
        run_id="run-v1",
        stage="contract",
        profile="smoke",
        config_id="cfg-v1",
        inputs={"dataset": ArtifactRef(kind="dataset", artifact_id="dataset-v1")},
        outputs={},
        seed=17,
        status="succeeded",
        started_at=now,
        completed_at=now,
        processed_tokens=12,
        processed_examples=3,
        optimizer_updates=0,
        device="cpu",
        software={"python": "3.14"},
        wall_time_seconds=0.01,
        peak_memory_bytes=0,
        cost_usd=0,
    )
    payload = record.model_dump(mode="json")
    assert payload["inputs"]["dataset"]["artifact_id"] == "dataset-v1"
    assert payload["started_at"].endswith("Z")
