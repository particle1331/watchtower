"""Small, reusable contracts for supervised and preference post-training."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

import torch
from torch import Tensor

from .logic import parse_proof, verify_proof

ChatRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One role-labelled message before tokenization."""

    role: ChatRole
    content: str


@dataclass(frozen=True, slots=True)
class RoleSpan:
    """Token interval and supervision status for one rendered message."""

    role: ChatRole
    start: int
    end: int
    supervised: bool


@dataclass(frozen=True, slots=True)
class SerializedChat:
    """Tokenized chat plus an explicit response-only loss mask."""

    token_ids: tuple[int, ...]
    loss_mask: tuple[bool, ...]
    spans: tuple[RoleSpan, ...]


def serialize_chat(
    messages: Sequence[ChatMessage],
    encode: Callable[[str], Sequence[int]],
    special_tokens: dict[str, int],
    *,
    supervise_roles: frozenset[ChatRole] = frozenset({"assistant"}),
) -> SerializedChat:
    """Render role markers and derive supervision from roles, not positions.

    ``special_tokens`` must contain ``bos``, ``eot`` and one marker named
    ``role_<role>`` for every message role. Assistant end-of-turn is included
    in the mask so generation learns when to stop; prompts and padding remain
    unsupervised.
    """

    required = {"bos", "eot"} | {f"role_{message.role}" for message in messages}
    missing = required - special_tokens.keys()
    if missing:
        raise ValueError(f"missing chat special tokens: {sorted(missing)}")
    token_ids: list[int] = [special_tokens["bos"]]
    loss_mask: list[bool] = [False]
    spans: list[RoleSpan] = []
    for message in messages:
        supervised = message.role in supervise_roles
        start = len(token_ids)
        token_ids.append(special_tokens[f"role_{message.role}"])
        loss_mask.append(False)
        encoded = list(encode(message.content))
        token_ids.extend(encoded)
        loss_mask.extend([supervised] * len(encoded))
        token_ids.append(special_tokens["eot"])
        loss_mask.append(supervised)
        spans.append(RoleSpan(message.role, start, len(token_ids), supervised))
    return SerializedChat(tuple(token_ids), tuple(loss_mask), tuple(spans))


@dataclass(frozen=True, slots=True)
class PreferencePair:
    """A prompt with a preferred and rejected completion."""

    prompt: str
    chosen: str
    rejected: str


def sequence_logprob(logits: Tensor, labels: Tensor, loss_mask: Tensor) -> Tensor:
    """Sum next-token log-probabilities over an explicit response mask."""

    if logits.ndim != 3 or labels.shape != loss_mask.shape or labels.shape != logits.shape[:2]:
        raise ValueError("logits, labels, and loss_mask have incompatible shapes")
    token_logprobs = torch.log_softmax(logits, dim=-1).gather(-1, labels[..., None]).squeeze(-1)
    return (token_logprobs * loss_mask.to(token_logprobs.dtype)).sum(dim=-1)


def dpo_loss(
    policy_chosen: Tensor,
    policy_rejected: Tensor,
    reference_chosen: Tensor,
    reference_rejected: Tensor,
    *,
    beta: float = 0.1,
) -> Tensor:
    """Return the per-example Direct Preference Optimization loss."""

    if beta <= 0:
        raise ValueError("beta must be positive")
    tensors = (policy_chosen, policy_rejected, reference_chosen, reference_rejected)
    if any(value.shape != policy_chosen.shape for value in tensors):
        raise ValueError("all preference log-probability tensors must have one shape")
    margin = beta * ((policy_chosen - reference_chosen) - (policy_rejected - reference_rejected))
    return -torch.nn.functional.logsigmoid(margin)


def group_normalized_advantages(rewards: Iterable[float], epsilon: float = 1e-8) -> Tensor:
    """Normalize a sampled reward group with its own mean and standard deviation."""

    values = torch.tensor(list(rewards), dtype=torch.float32)
    if values.numel() == 0:
        raise ValueError("reward group must not be empty")
    if epsilon <= 0:
        raise ValueError("epsilon must be positive")
    return (values - values.mean()) / (values.std(unbiased=False) + epsilon)


def verifier_reward(proof_text: str) -> float:
    """Score a rendered proof with the independent checker, returning 0 or 1."""

    try:
        return float(verify_proof(parse_proof(proof_text)).valid)
    except ValueError:
        return 0.0
