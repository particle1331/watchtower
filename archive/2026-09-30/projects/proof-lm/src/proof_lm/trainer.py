"""Deterministic training steps and exact-resume checkpoint helpers."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch import Tensor

from .data.batching import PackedBatch
from .model import ProofLM


@dataclass(frozen=True, slots=True)
class TrainerState:
    step: int = 0
    processed_tokens: int = 0
    processed_examples: int = 0


def _batch_tensors(batch: PackedBatch, device: torch.device) -> tuple[Tensor, Tensor, Tensor]:
    inputs = torch.tensor(batch.input_ids, dtype=torch.long, device=device)
    targets = torch.tensor(batch.target_ids, dtype=torch.long, device=device)
    loss_mask = torch.tensor(batch.loss_mask, dtype=torch.bool, device=device)
    return inputs, targets, loss_mask


def train_batches(
    model: ProofLM,
    batches: list[PackedBatch],
    optimizer: torch.optim.Optimizer,
    *,
    state: TrainerState | None = None,
    max_steps: int | None = None,
    device: str | torch.device = "cpu",
) -> tuple[TrainerState, list[float]]:
    """Run an ordered batch sequence and return state plus scalar losses."""

    device = torch.device(device)
    model.to(device).train()
    state = state or TrainerState()
    losses = []
    limit = len(batches) if max_steps is None else min(max_steps, len(batches))
    for batch in batches[:limit]:
        inputs, targets, loss_mask = _batch_tensors(batch, device)
        optimizer.zero_grad(set_to_none=True)
        _, loss = model(inputs, labels=targets, loss_mask=loss_mask)
        if loss is None:
            raise RuntimeError("model did not return a loss for labeled training")
        loss.backward()
        optimizer.step()
        state = TrainerState(
            step=state.step + 1,
            processed_tokens=state.processed_tokens + int(loss_mask.sum().item()),
            processed_examples=state.processed_examples + len(batch.input_ids),
        )
        losses.append(float(loss.detach().cpu()))
    return state, losses


def save_training_checkpoint(
    path: str | Path,
    model: ProofLM,
    optimizer: torch.optim.Optimizer,
    state: TrainerState,
) -> None:
    """Save model, optimizer, counters, and all RNG states needed for resume."""

    checkpoint = {
        "model_config": model.config.__dict__ if hasattr(model.config, "__dict__") else {
            field: getattr(model.config, field)
            for field in model.config.__dataclass_fields__
        },
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "trainer_state": state,
        "torch_rng_state": torch.get_rng_state(),
        "numpy_rng_state": np.random.get_state(),
        "python_rng_state": random.getstate(),
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, output)


def load_training_checkpoint(
    path: str | Path,
    model: ProofLM,
    optimizer: torch.optim.Optimizer,
) -> TrainerState:
    """Restore state and RNG streams into already-constructed objects."""

    checkpoint: dict[str, Any] = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model"])
    optimizer.load_state_dict(checkpoint["optimizer"])
    torch.set_rng_state(checkpoint["torch_rng_state"])
    np.random.set_state(checkpoint["numpy_rng_state"])
    random.setstate(checkpoint["python_rng_state"])
    return checkpoint["trainer_state"]
