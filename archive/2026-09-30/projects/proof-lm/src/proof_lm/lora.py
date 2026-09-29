"""Minimal LoRA injection with explicit merge and adapter-only state."""

from __future__ import annotations

from collections.abc import Iterable

import torch
from torch import Tensor, nn
from torch.nn import functional as F


class LoRALinear(nn.Module):
    """A frozen linear layer plus a low-rank residual update."""

    def __init__(self, base: nn.Linear, rank: int, alpha: float = 1.0, dropout: float = 0.0) -> None:
        super().__init__()
        if rank < 1 or alpha <= 0 or not 0 <= dropout < 1:
            raise ValueError("rank and alpha must be positive; dropout must be in [0, 1)")
        self.base = base
        self.rank = rank
        self.alpha = alpha
        self.scaling = alpha / rank
        self.dropout = nn.Dropout(dropout)
        for parameter in self.base.parameters():
            parameter.requires_grad_(False)
        self.lora_A = nn.Parameter(torch.empty(rank, base.in_features, device=base.weight.device))
        self.lora_B = nn.Parameter(torch.zeros(base.out_features, rank, device=base.weight.device))
        nn.init.kaiming_uniform_(self.lora_A, a=5**0.5)
        self.merged = False

    def forward(self, values: Tensor) -> Tensor:
        result = self.base(values)
        if not self.merged:
            result = result + F.linear(F.linear(self.dropout(values), self.lora_A), self.lora_B) * self.scaling
        return result

    def delta_weight(self) -> Tensor:
        return self.lora_B @ self.lora_A * self.scaling

    @torch.no_grad()
    def merge(self) -> None:
        if not self.merged:
            self.base.weight.add_(self.delta_weight().to(self.base.weight.dtype))
            self.merged = True

    @torch.no_grad()
    def unmerge(self) -> None:
        if self.merged:
            self.base.weight.sub_(self.delta_weight().to(self.base.weight.dtype))
            self.merged = False


def _replace(parent: nn.Module, name: str, replacement: nn.Module) -> None:
    if name.isdigit():
        parent[int(name)] = replacement  # type: ignore[index]
    else:
        setattr(parent, name, replacement)


def inject_lora(
    module: nn.Module,
    *,
    rank: int,
    alpha: float = 1.0,
    dropout: float = 0.0,
    target_names: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Replace selected Linear modules and return their qualified names."""

    requested = set(target_names) if target_names is not None else None
    matches: list[str] = []
    for qualified_name, child in list(module.named_modules()):
        if not qualified_name or not isinstance(child, nn.Linear):
            continue
        if requested is not None and qualified_name not in requested:
            continue
        parent_name, _, child_name = qualified_name.rpartition(".")
        parent = module.get_submodule(parent_name) if parent_name else module
        _replace(parent, child_name, LoRALinear(child, rank, alpha, dropout))
        matches.append(qualified_name)
    if not matches:
        raise ValueError("no matching Linear modules for LoRA injection")
    return tuple(matches)


def lora_modules(module: nn.Module) -> tuple[LoRALinear, ...]:
    return tuple(child for child in module.modules() if isinstance(child, LoRALinear))


def adapter_state_dict(module: nn.Module) -> dict[str, Tensor]:
    """Extract only LoRA factors, so a small adapter can travel separately."""

    result: dict[str, Tensor] = {}
    for name, child in module.named_modules():
        if isinstance(child, LoRALinear):
            prefix = f"{name}." if name else ""
            result[f"{prefix}lora_A"] = child.lora_A.detach().clone()
            result[f"{prefix}lora_B"] = child.lora_B.detach().clone()
    return result


def merge_lora(module: nn.Module) -> None:
    for child in lora_modules(module):
        child.merge()


def unmerge_lora(module: nn.Module) -> None:
    for child in lora_modules(module):
        child.unmerge()


def trainable_parameter_count(module: nn.Module) -> int:
    return sum(parameter.numel() for parameter in module.parameters() if parameter.requires_grad)
