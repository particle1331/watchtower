"""Benchmark the Phase 0 contract workload locally.

This is intentionally a schema and identity benchmark, not a claim about model
training speed. The model smoke benchmark belongs after the trainer exists.
"""

from __future__ import annotations

import json
from time import perf_counter

from .config import load_config
from .schemas import (
    CHECKPOINT_SCHEMA,
    DATASET_SCHEMA,
    REPORT_SCHEMA,
    TOKENIZER_SCHEMA,
    CheckpointManifest,
    CheckpointState,
    CostMetadata,
    DatasetManifest,
    EvaluatorReport,
    SplitManifest,
    TokenizerManifest,
    validate_evaluation_bundle,
)

_DIGEST = "0" * 64


def reference_bundle() -> tuple[CheckpointManifest, TokenizerManifest, DatasetManifest]:
    """Build the smallest valid cross-artifact bundle for contract tests."""

    tokenizer = TokenizerManifest(
        schema_version=TOKENIZER_SCHEMA,
        tokenizer_id="tok-smoke-v1",
        revision="fixture-v1",
        vocab_size=128,
        vocabulary_sha256=_DIGEST,
        merges_sha256=_DIGEST,
        normalizer_version="unicode-casefold-v1",
        special_tokens={"<pad>": 0, "<eos>": 1},
        training_dataset_id="dataset-smoke-v1",
        tokenizer_sha256=_DIGEST,
    )
    dataset = DatasetManifest(
        schema_version=DATASET_SCHEMA,
        dataset_manifest_id="dataset-smoke-v1",
        source_revision="fixture-v1",
        license="course-fixture",
        generator_version="none",
        normalization_version="unicode-casefold-v1",
        content_sha256=_DIGEST,
        splits={
            "train": SplitManifest(
                examples=2, token_count=8, structural_keys_sha256=_DIGEST
            ),
            "test": SplitManifest(
                examples=1, token_count=4, structural_keys_sha256=_DIGEST
            ),
        },
        total_examples=3,
        total_tokens=12,
    )
    checkpoint = CheckpointManifest(
        schema_version=CHECKPOINT_SCHEMA,
        checkpoint_id="ckpt-smoke-v1",
        stage="base-pretraining",
        profile="smoke",
        config_id=load_config("smoke").config_id,
        model_config_id="model-smoke-v1",
        tokenizer_id=tokenizer.tokenizer_id,
        dataset_manifest_id=dataset.dataset_manifest_id,
        lineage=("ckpt-smoke-v1",),
        state=CheckpointState(
            model="checkpoints/ckpt-smoke-v1/model.pt",
            optimizer="checkpoints/ckpt-smoke-v1/optimizer.pt",
            scheduler="checkpoints/ckpt-smoke-v1/scheduler.json",
            scaler=None,
            data_cursor="checkpoints/ckpt-smoke-v1/data-cursor.json",
            rng_state="checkpoints/ckpt-smoke-v1/rng-state.pt",
        ),
        cost=CostMetadata(
            device="cpu",
            wall_time_seconds=0,
            peak_memory_bytes=0,
            gpu_dollars_per_hour=0,
            cost_usd=0,
        ),
    )
    return checkpoint, tokenizer, dataset


def run_contract_benchmark(iterations: int = 256) -> dict[str, float | int | str]:
    """Validate and serialize one fixed bundle repeatedly, returning metrics."""

    if iterations < 1:
        raise ValueError("iterations must be positive")
    checkpoint, tokenizer, dataset = reference_bundle()
    report = EvaluatorReport(
        schema_version=REPORT_SCHEMA,
        report_id="report-smoke-contract-v1",
        checkpoint_id=checkpoint.checkpoint_id,
        tokenizer_id=tokenizer.tokenizer_id,
        dataset_manifest_id=dataset.dataset_manifest_id,
        evaluator_id="evaluator-smoke-v1",
        evaluator_version="1",
        decoding_config_id="decode-greedy-v1",
        seed=17,
        suites={"contract": {"identity_valid": 1.0}},
        accepted=True,
    )
    started = perf_counter()
    serialized_bytes = 0
    for _ in range(iterations):
        validate_evaluation_bundle(
            report,
            checkpoint,
            tokenizer,
            dataset,
            evaluator_id="evaluator-smoke-v1",
            evaluator_version="1",
        )
        serialized_bytes += len(report.model_dump_json())
    elapsed = perf_counter() - started
    config = load_config("smoke")
    return {
        "profile": config.name,
        "iterations": iterations,
        "elapsed_seconds": elapsed,
        "records_per_second": iterations / elapsed,
        "serialized_bytes": serialized_bytes,
    }


def main() -> None:
    """Print a machine-readable Phase 0 contract benchmark."""

    print(json.dumps(run_contract_benchmark(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
