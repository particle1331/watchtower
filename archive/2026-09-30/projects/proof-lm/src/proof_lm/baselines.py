"""PyTorch baseline models used before the full decoder."""

from __future__ import annotations

from collections.abc import Iterable

import torch
from torch import Tensor, nn


def make_context_dataset(tokens: Iterable[int], context_length: int) -> tuple[Tensor, Tensor]:
    """Create shifted fixed-context tensors for a baseline model."""

    values = torch.tensor(list(tokens), dtype=torch.long)
    if context_length < 1:
        raise ValueError("context_length must be positive")
    if values.numel() <= context_length:
        return torch.empty((0, context_length), dtype=torch.long), torch.empty(0, dtype=torch.long)
    inputs = torch.stack(
        [values[start : start + context_length] for start in range(len(values) - context_length)]
    )
    return inputs, values[context_length:]


class TorchBigramLM(nn.Module):
    """One learnable categorical distribution per preceding token."""

    def __init__(self, vocab_size: int) -> None:
        super().__init__()
        self.logits = nn.Parameter(torch.zeros(vocab_size, vocab_size))

    def forward(self, previous: Tensor) -> Tensor:
        return self.logits[previous]


class TorchContextMLP(nn.Module):
    """Fixed-context embedding MLP baseline with explicit receptive field."""

    def __init__(
        self,
        vocab_size: int,
        context_length: int,
        embedding_dim: int = 16,
        hidden_dim: int = 64,
    ) -> None:
        super().__init__()
        self.context_length = context_length
        self.embedding = nn.Embedding(vocab_size, embedding_dim)
        self.hidden = nn.Linear(context_length * embedding_dim, hidden_dim)
        self.output = nn.Linear(hidden_dim, vocab_size)

    def forward(self, context: Tensor) -> Tensor:
        if context.ndim != 2 or context.shape[1] != self.context_length:
            raise ValueError("context must have shape (batch, context_length)")
        values = self.embedding(context).reshape(context.shape[0], -1)
        return self.output(torch.tanh(self.hidden(values)))


def train_classifier(
    model: nn.Module,
    inputs: Tensor,
    targets: Tensor,
    *,
    steps: int,
    learning_rate: float,
) -> list[float]:
    """Train a baseline with the same explicit full-batch objective each step."""

    if steps < 1 or inputs.shape[0] == 0:
        raise ValueError("steps and the training batch must be positive")
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
    losses = []
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.cross_entropy(model(inputs), targets)
        loss.backward()
        optimizer.step()
        losses.append(float(loss.detach()))
    return losses
