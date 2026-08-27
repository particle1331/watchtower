"""Optimizer schedules and measurements shared by ProofLM trainers."""

from __future__ import annotations

import math
from collections.abc import Iterable

import torch
from torch import Tensor, nn


def warmup_cosine_factor(
    update: int,
    *,
    warmup_updates: int,
    total_updates: int,
    minimum_ratio: float = 0.1,
) -> float:
    """Return a warmup-then-cosine multiplier for one optimizer update."""

    if update < 0 or warmup_updates < 0 or total_updates < 1:
        raise ValueError("update and schedule counts must be non-negative")
    if not 0 <= minimum_ratio <= 1:
        raise ValueError("minimum_ratio must be in [0, 1]")
    if update < warmup_updates and warmup_updates:
        return (update + 1) / warmup_updates
    progress = min(
        1.0,
        max(0.0, (update - warmup_updates) / max(1, total_updates - warmup_updates)),
    )
    return minimum_ratio + (1 - minimum_ratio) * 0.5 * (1 + math.cos(math.pi * progress))


def global_gradient_norm(parameters: Iterable[nn.Parameter]) -> Tensor:
    """Measure the L2 norm of all finite gradients as one vector."""

    gradients = [parameter.grad.detach() for parameter in parameters if parameter.grad is not None]
    if not gradients:
        return torch.tensor(0.0)
    return torch.linalg.vector_norm(torch.stack([torch.linalg.vector_norm(g) for g in gradients]))


def clip_gradients(parameters: Iterable[nn.Parameter], maximum_norm: float) -> float:
    """Clip one global norm and return the pre-clipping value."""

    if maximum_norm <= 0:
        raise ValueError("maximum_norm must be positive")
    parameters = list(parameters)
    norm = global_gradient_norm(parameters)
    torch.nn.utils.clip_grad_norm_(parameters, maximum_norm)
    return float(norm)


def adamw_parameter_groups(
    model: nn.Module, weight_decay: float
) -> list[dict[str, object]]:
    """Separate matrix weights from biases and normalization parameters."""

    decay, no_decay = [], []
    for name, parameter in model.named_parameters():
        if not parameter.requires_grad:
            continue
        if name.endswith("bias") or "norm" in name.lower() or parameter.ndim < 2:
            no_decay.append(parameter)
        else:
            decay.append(parameter)
    return [
        {"params": decay, "weight_decay": weight_decay},
        {"params": no_decay, "weight_decay": 0.0},
    ]
