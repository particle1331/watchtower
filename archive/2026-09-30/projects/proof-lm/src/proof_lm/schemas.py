"""Versioned schemas for the first ProofLM artifact boundary.

The schemas intentionally describe identities and metadata rather than tensor
contents. Checkpoint files can remain in ignored artifact storage while their
manifest records the state components and inputs required to reproduce them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .identity import identity

SCHEMA_VERSION = "proof-lm/v1"
CONFIG_SCHEMA: Literal["proof-lm/v1/config"] = "proof-lm/v1/config"
TOKENIZER_SCHEMA: Literal["proof-lm/v1/tokenizer"] = "proof-lm/v1/tokenizer"
DATASET_SCHEMA: Literal["proof-lm/v1/dataset"] = "proof-lm/v1/dataset"
CHECKPOINT_SCHEMA: Literal["proof-lm/v1/checkpoint"] = "proof-lm/v1/checkpoint"
EXPERIMENT_SCHEMA: Literal["proof-lm/v1/experiment"] = "proof-lm/v1/experiment"
REPORT_SCHEMA: Literal["proof-lm/v1/report"] = "proof-lm/v1/report"
TOOL_TRACE_SCHEMA: Literal["proof-lm/v1/tool-trace"] = "proof-lm/v1/tool-trace"

ArtifactKind = Literal[
    "config",
    "tokenizer",
    "dataset",
    "checkpoint",
    "evaluator",
    "report",
    "tool_trace",
]


class ProofLMModel(BaseModel):
    """Architecture fields shared by smoke and standard configurations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    vocab_size: int = Field(gt=0)
    context_length: int = Field(gt=0)
    n_layers: int = Field(gt=0)
    d_model: int = Field(gt=0)
    n_heads: int = Field(gt=0)
    d_head: int = Field(gt=0)
    d_ff: int = Field(gt=0)
    normalization: Literal["layer_norm"]
    position_encoding: Literal["rope"]
    activation: Literal["gelu"]
    dropout: float = Field(ge=0, lt=1)
    tie_embeddings: bool
    bias: bool

    @model_validator(mode="after")
    def validate_attention_width(self) -> ProofLMModel:
        if self.n_heads * self.d_head != self.d_model:
            raise ValueError("n_heads * d_head must equal d_model")
        return self


class TrainingConfig(BaseModel):
    """Budget and optimizer settings that affect a training trajectory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objective: Literal["causal_language_modeling"]
    optimizer: Literal["adamw"]
    precision: Literal["fp32", "bf16"]
    token_budget: int = Field(gt=0)
    microbatch_size: int = Field(gt=0)
    gradient_accumulation: int = Field(gt=0)
    learning_rate: float = Field(gt=0)
    weight_decay: float = Field(ge=0)
    warmup_updates: int = Field(ge=0)
    max_updates: int = Field(gt=0)
    seed: int = Field(ge=0)


class DataBinding(BaseModel):
    """Named inputs a profile expects to consume."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_manifest_id: str = Field(min_length=1)
    tokenizer_id: str = Field(min_length=1)
    evaluator_id: str = Field(min_length=1)


class RunConfig(BaseModel):
    """A complete, named execution profile."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proof-lm/v1/config"]
    name: Literal["smoke", "standard"]
    device: Literal["cpu", "cuda"]
    artifact_root: str = Field(min_length=1)
    output_namespace: str = Field(min_length=1)
    model: ProofLMModel
    training: TrainingConfig
    data: DataBinding

    @property
    def config_id(self) -> str:
        return identity("cfg", self.model_dump(mode="json"))


class ArtifactRef(BaseModel):
    """A reference stored in a run record or report."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ArtifactKind
    artifact_id: str = Field(min_length=1)
    sha256: str | None = Field(default=None, min_length=64, max_length=64)


class TokenizerManifest(BaseModel):
    """Frozen tokenizer identity consumed by every model checkpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proof-lm/v1/tokenizer"]
    tokenizer_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    vocab_size: int = Field(gt=0)
    vocabulary_sha256: str = Field(min_length=64, max_length=64)
    merges_sha256: str = Field(min_length=64, max_length=64)
    normalizer_version: str = Field(min_length=1)
    special_tokens: dict[str, int]
    training_dataset_id: str = Field(min_length=1)
    tokenizer_sha256: str = Field(min_length=64, max_length=64)

    @field_validator("special_tokens")
    @classmethod
    def validate_special_tokens(cls, value: dict[str, int]) -> dict[str, int]:
        if not value or len(set(value.values())) != len(value):
            raise ValueError("special token names and IDs must be non-empty and unique")
        return value


class SplitManifest(BaseModel):
    """Counts and structural identity for one dataset partition."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    examples: int = Field(ge=0)
    token_count: int = Field(ge=0)
    structural_keys_sha256: str = Field(min_length=64, max_length=64)


class DatasetManifest(BaseModel):
    """Versioned provenance and split contract for a dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proof-lm/v1/dataset"]
    dataset_manifest_id: str = Field(min_length=1)
    source_revision: str = Field(min_length=1)
    license: str = Field(min_length=1)
    generator_version: str = Field(min_length=1)
    normalization_version: str = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    splits: dict[str, SplitManifest]
    total_examples: int = Field(ge=0)
    total_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_split_totals(self) -> DatasetManifest:
        if not self.splits:
            raise ValueError("dataset manifest must contain at least one split")
        if sum(split.examples for split in self.splits.values()) != self.total_examples:
            raise ValueError("split example counts must sum to total_examples")
        if sum(split.token_count for split in self.splits.values()) != self.total_tokens:
            raise ValueError("split token counts must sum to total_tokens")
        return self


class CheckpointState(BaseModel):
    """Paths for all state needed for an exact resume."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str = Field(min_length=1)
    optimizer: str = Field(min_length=1)
    scheduler: str = Field(min_length=1)
    scaler: str | None
    data_cursor: str = Field(min_length=1)
    rng_state: str = Field(min_length=1)


class CostMetadata(BaseModel):
    """Measured resource facts attached to an artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    device: str = Field(min_length=1)
    wall_time_seconds: float = Field(ge=0)
    peak_memory_bytes: int = Field(ge=0)
    gpu_dollars_per_hour: float = Field(ge=0)
    cost_usd: float = Field(ge=0)


class CheckpointManifest(BaseModel):
    """Checkpoint metadata, lineage, and exact-resume state inventory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proof-lm/v1/checkpoint"]
    checkpoint_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    profile: Literal["smoke", "standard"]
    config_id: str = Field(min_length=1)
    model_config_id: str = Field(min_length=1)
    tokenizer_id: str = Field(min_length=1)
    dataset_manifest_id: str = Field(min_length=1)
    parent_checkpoint_id: str | None = None
    lineage: tuple[str, ...] = Field(min_length=1)
    state: CheckpointState
    cost: CostMetadata
    metrics: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_lineage(self) -> CheckpointManifest:
        if self.lineage[-1] != self.checkpoint_id:
            raise ValueError("checkpoint lineage must end with checkpoint_id")
        if self.parent_checkpoint_id is not None and (
            len(self.lineage) < 2 or self.lineage[-2] != self.parent_checkpoint_id
        ):
            raise ValueError("parent checkpoint must be the preceding lineage entry")
        return self


class ExperimentRecord(BaseModel):
    """Run-level evidence shared by training and evaluation stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proof-lm/v1/experiment"]
    run_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    profile: Literal["smoke", "standard"]
    config_id: str = Field(min_length=1)
    inputs: dict[str, ArtifactRef]
    outputs: dict[str, ArtifactRef]
    seed: int = Field(ge=0)
    status: Literal["running", "succeeded", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    processed_tokens: int = Field(ge=0)
    processed_examples: int = Field(ge=0)
    optimizer_updates: int = Field(ge=0)
    device: str = Field(min_length=1)
    software: dict[str, str]
    wall_time_seconds: float = Field(ge=0)
    peak_memory_bytes: int = Field(ge=0)
    cost_usd: float = Field(ge=0)
    parent_checkpoint_id: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_completion(self) -> ExperimentRecord:
        if self.status == "succeeded" and self.completed_at is None:
            raise ValueError("succeeded experiment records need completed_at")
        return self


class EvaluatorReport(BaseModel):
    """Stored metrics for a frozen evaluator and explicit input identities."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proof-lm/v1/report"]
    report_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    tokenizer_id: str = Field(min_length=1)
    dataset_manifest_id: str = Field(min_length=1)
    evaluator_id: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    decoding_config_id: str = Field(min_length=1)
    seed: int = Field(ge=0)
    suites: dict[str, dict[str, float]]
    metrics: dict[str, float] = Field(default_factory=dict)
    accepted: bool
    metadata: dict[str, str] = Field(default_factory=dict)


class ToolTrace(BaseModel):
    """One step in a typed proof-tool episode."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["proof-lm/v1/tool-trace"]
    trace_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    step: int = Field(ge=0)
    checkpoint_id: str = Field(min_length=1)
    tool_registry_id: str = Field(min_length=1)
    request: str = Field(min_length=1)
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    status: Literal["no_call", "called", "rejected", "error", "completed"]
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_result_shape(self) -> ToolTrace:
        if self.status in {"called", "completed"} and self.tool_name is None:
            raise ValueError("called and completed traces need a tool_name")
        if self.status in {"rejected", "error"} and not self.error_code:
            raise ValueError("rejected and error traces need an error_code")
        return self


class ArtifactIdentityError(ValueError):
    """Raised when a report combines artifacts from incompatible lineages."""


def validate_evaluation_bundle(
    report: EvaluatorReport,
    checkpoint: CheckpointManifest,
    tokenizer: TokenizerManifest,
    dataset: DatasetManifest,
    evaluator_id: str,
    evaluator_version: str,
) -> None:
    """Reject a report whose declared inputs do not match supplied artifacts."""

    expected = {
        "checkpoint": (report.checkpoint_id, checkpoint.checkpoint_id),
        "tokenizer/report": (report.tokenizer_id, tokenizer.tokenizer_id),
        "tokenizer/checkpoint": (checkpoint.tokenizer_id, tokenizer.tokenizer_id),
        "dataset": (report.dataset_manifest_id, dataset.dataset_manifest_id),
        "evaluator id": (report.evaluator_id, evaluator_id),
        "evaluator version": (report.evaluator_version, evaluator_version),
    }
    mismatches = [name for name, (declared, actual) in expected.items() if declared != actual]
    if mismatches:
        raise ArtifactIdentityError("incompatible evaluation artifacts: " + ", ".join(mismatches))
