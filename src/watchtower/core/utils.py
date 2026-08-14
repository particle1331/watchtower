"""Reproducibility helpers for ML notebooks."""

from __future__ import annotations

import random

import numpy as np
import torch


def set_seed(value: int = 42, deterministic: bool = False) -> None:
    """Seed Python, NumPy, and PyTorch for reproducibility.

    WARNING: Setting *deterministic* to True may decrease performance:
    disabling benchmarking causes cuDNN to deterministically select an
    algorithm, possibly at the cost of reduced performance.
    """
    random.seed(value)
    np.random.seed(value)
    torch.manual_seed(value)

    if deterministic:
        torch.backends.cudnn.benchmark = False
        torch.use_deterministic_algorithms(True)
    else:
        torch.backends.cudnn.benchmark = True
        torch.use_deterministic_algorithms(False)

    print(f"seed: {value}  deterministic: {deterministic}")
