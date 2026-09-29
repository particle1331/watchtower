"""Shared contracts and utilities for the ProofLM course project."""

from .model import DecoderConfig, ProofLM
from .posttraining import (
    ChatMessage,
    PreferencePair,
    dpo_loss,
    group_normalized_advantages,
    serialize_chat,
    verifier_reward,
)
from .schemas import (
    CheckpointManifest,
    DatasetManifest,
    EvaluatorReport,
    ExperimentRecord,
    RunConfig,
    TokenizerManifest,
    ToolTrace,
)

__all__ = [
    "CheckpointManifest",
    "ChatMessage",
    "DecoderConfig",
    "DatasetManifest",
    "EvaluatorReport",
    "ExperimentRecord",
    "RunConfig",
    "TokenizerManifest",
    "ToolTrace",
    "ProofLM",
    "PreferencePair",
    "dpo_loss",
    "group_normalized_advantages",
    "serialize_chat",
    "verifier_reward",
]
