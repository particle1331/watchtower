"""Shared likelihood and proof-fixture evaluation helpers."""

from __future__ import annotations

import math
from collections.abc import Iterable

import torch

from .data.batching import PackedBatch
from .identity import identity
from .logic import GeneratedExample, verify_proof
from .model import ProofLM


def evaluate_language_model(
    model: ProofLM,
    batches: Iterable[PackedBatch],
    *,
    device: str = "cpu",
) -> dict[str, float | str]:
    """Return masked next-token loss, perplexity, and evaluator identity."""

    model = model.to(device).eval()
    losses = []
    token_count = 0
    with torch.no_grad():
        for batch in batches:
            inputs = torch.tensor(batch.input_ids, dtype=torch.long, device=device)
            targets = torch.tensor(batch.target_ids, dtype=torch.long, device=device)
            loss_mask = torch.tensor(batch.loss_mask, dtype=torch.bool, device=device)
            _, loss = model(inputs, labels=targets, loss_mask=loss_mask)
            if loss is not None:
                losses.append(float(loss.cpu()))
            token_count += int(loss_mask.sum().item())
    mean_loss = sum(losses) / max(len(losses), 1)
    return {
        "evaluator_id": identity("eval", {"name": "masked-next-token-v1"}),
        "loss": mean_loss,
        "perplexity": math.exp(min(mean_loss, 20.0)),
        "tokens": float(token_count),
    }


def evaluate_proof_fixtures(examples: Iterable[GeneratedExample]) -> dict[str, float | str]:
    """Score generated fixture validity independently of model likelihood."""

    examples = list(examples)
    positives = [example for example in examples if example.kind == "positive"]
    negatives = [example for example in examples if example.kind == "negative"]
    positive_valid = sum(verify_proof(example.proof).valid for example in positives)
    negative_rejected = sum(not verify_proof(example.proof).valid for example in negatives)
    return {
        "evaluator_id": identity("eval", {"name": "proof-verifier-v1"}),
        "positive_validity": positive_valid / max(len(positives), 1),
        "negative_rejection": negative_rejected / max(len(negatives), 1),
        "examples": float(len(examples)),
    }
