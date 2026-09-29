"""Small decoder-only Transformer used by the ProofLM course."""

from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import Tensor, nn
from torch.nn import functional as F


@dataclass(frozen=True, slots=True)
class DecoderConfig:
    vocab_size: int
    context_length: int
    n_layers: int = 2
    d_model: int = 128
    n_heads: int = 4
    d_ff: int = 512
    dropout: float = 0.0
    bias: bool = True
    tie_embeddings: bool = True

    def __post_init__(self) -> None:
        if self.d_model % self.n_heads:
            raise ValueError("d_model must be divisible by n_heads")
        if self.d_model // self.n_heads % 2:
            raise ValueError("each attention head must have an even width for RoPE")
        if self.vocab_size < 1 or self.context_length < 1:
            raise ValueError("vocab_size and context_length must be positive")


class RotaryEmbedding(nn.Module):
    """Apply rotary position embeddings to query and key channels."""

    def __init__(self, head_width: int, base: float = 10_000.0) -> None:
        super().__init__()
        inverse_frequency = 1.0 / (
            base ** (torch.arange(0, head_width, 2, dtype=torch.float32) / head_width)
        )
        self.register_buffer("inverse_frequency", inverse_frequency, persistent=False)

    def forward(self, values: Tensor) -> Tensor:
        _, _, time, head_width = values.shape
        inverse_frequency = self.get_buffer("inverse_frequency")
        positions = torch.arange(time, device=values.device, dtype=torch.float32)
        angles = torch.einsum("t,d->td", positions, inverse_frequency)
        cosines = angles.cos()[None, None, :, :]
        sines = angles.sin()[None, None, :, :]
        first, second = values[..., ::2], values[..., 1::2]
        return torch.stack(
            (first * cosines - second * sines, first * sines + second * cosines), dim=-1
        ).flatten(-2).reshape(values.shape[0], values.shape[1], time, head_width)


class CausalSelfAttention(nn.Module):
    def __init__(self, config: DecoderConfig) -> None:
        super().__init__()
        self.heads = config.n_heads
        self.head_width = config.d_model // config.n_heads
        self.query_key_value = nn.Linear(config.d_model, 3 * config.d_model, bias=config.bias)
        self.output = nn.Linear(config.d_model, config.d_model, bias=config.bias)
        self.dropout = nn.Dropout(config.dropout)
        self.rotary = RotaryEmbedding(self.head_width)
        self.register_buffer(
            "causal_mask",
            torch.tril(torch.ones(config.context_length, config.context_length, dtype=torch.bool)),
            persistent=False,
        )

    def forward(self, hidden: Tensor, attention_mask: Tensor | None = None) -> Tensor:
        batch, time, width = hidden.shape
        causal_mask = self.get_buffer("causal_mask")
        if time > causal_mask.shape[0]:
            raise ValueError("sequence length exceeds model context_length")
        query, key, value = self.query_key_value(hidden).split(width, dim=-1)
        query = query.view(batch, time, self.heads, self.head_width).transpose(1, 2)
        key = key.view(batch, time, self.heads, self.head_width).transpose(1, 2)
        value = value.view(batch, time, self.heads, self.head_width).transpose(1, 2)
        query = self.rotary(query)
        key = self.rotary(key)
        scores = query @ key.transpose(-2, -1) / math.sqrt(self.head_width)
        allowed = causal_mask[:time, :time][None, None, :, :]
        if attention_mask is not None:
            key_mask = attention_mask[:, None, None, :time].to(torch.bool)
            allowed = allowed & key_mask
        scores = scores.masked_fill(~allowed, torch.finfo(scores.dtype).min)
        weights = F.softmax(scores, dim=-1)
        weights = self.dropout(weights)
        attended = (weights @ value).transpose(1, 2).reshape(batch, time, width)
        if attention_mask is not None:
            attended = attended * attention_mask[:, :time, None].to(attended.dtype)
        return self.output(attended)


class DecoderBlock(nn.Module):
    def __init__(self, config: DecoderConfig) -> None:
        super().__init__()
        self.attention_norm = nn.LayerNorm(config.d_model, elementwise_affine=True)
        self.attention = CausalSelfAttention(config)
        self.feed_forward_norm = nn.LayerNorm(config.d_model, elementwise_affine=True)
        self.feed_forward = nn.Sequential(
            nn.Linear(config.d_model, config.d_ff, bias=config.bias),
            nn.GELU(),
            nn.Linear(config.d_ff, config.d_model, bias=config.bias),
            nn.Dropout(config.dropout),
        )

    def forward(self, hidden: Tensor, attention_mask: Tensor | None = None) -> Tensor:
        hidden = hidden + self.attention(self.attention_norm(hidden), attention_mask)
        return hidden + self.feed_forward(self.feed_forward_norm(hidden))


class ProofLM(nn.Module):
    """Decoder-only language model with a stable, inspectable architecture."""

    def __init__(self, config: DecoderConfig) -> None:
        super().__init__()
        self.config = config
        self.token_embedding = nn.Embedding(config.vocab_size, config.d_model)
        self.blocks = nn.ModuleList(DecoderBlock(config) for _ in range(config.n_layers))
        self.final_norm = nn.LayerNorm(config.d_model)
        self.lm_head = nn.Linear(config.d_model, config.vocab_size, bias=False)
        if config.tie_embeddings:
            self.lm_head.weight = self.token_embedding.weight
        self.apply(self._initialize)

    @staticmethod
    def _initialize(module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(module.weight, mean=0.0, std=0.02)

    def forward(
        self,
        input_ids: Tensor,
        *,
        attention_mask: Tensor | None = None,
        labels: Tensor | None = None,
        loss_mask: Tensor | None = None,
    ) -> tuple[Tensor, Tensor | None]:
        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape (batch, time)")
        hidden = self.token_embedding(input_ids)
        for block in self.blocks:
            hidden = block(hidden, attention_mask)
        logits = self.lm_head(self.final_norm(hidden))
        if labels is None:
            return logits, None
        token_losses = F.cross_entropy(
            logits.reshape(-1, logits.shape[-1]), labels.reshape(-1), reduction="none"
        ).reshape_as(labels)
        if loss_mask is None:
            loss_mask = torch.ones_like(token_losses, dtype=torch.bool)
        weights = loss_mask.to(token_losses.dtype)
        loss = (token_losses * weights).sum() / weights.sum().clamp_min(1.0)
        return logits, loss

    @torch.no_grad()
    def generate(
        self,
        input_ids: Tensor,
        steps: int,
        *,
        temperature: float = 1.0,
        top_k: int | None = None,
        generator: torch.Generator | None = None,
    ) -> Tensor:
        if temperature <= 0:
            raise ValueError("temperature must be positive")
        self.eval()
        generated = input_ids
        for _ in range(steps):
            context = generated[:, -self.config.context_length :]
            logits = self(context)[0][:, -1] / temperature
            if top_k is not None:
                values, indices = torch.topk(logits, min(top_k, logits.shape[-1]), dim=-1)
                filtered = torch.full_like(logits, torch.finfo(logits.dtype).min)
                filtered.scatter_(1, indices, values)
                logits = filtered
            probabilities = F.softmax(logits, dim=-1)
            next_token = torch.multinomial(probabilities, 1, generator=generator)
            generated = torch.cat((generated, next_token), dim=1)
        return generated

    @property
    def parameter_count(self) -> int:
        return sum(parameter.numel() for parameter in self.parameters())

    @property
    def embeddings_are_tied(self) -> bool:
        return self.lm_head.weight.data_ptr() == self.token_embedding.weight.data_ptr()
