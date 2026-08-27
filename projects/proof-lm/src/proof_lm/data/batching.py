"""Packed causal examples with explicit document-boundary loss masks."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PackedExample:
    """One fixed-width next-token example and its loss/validity masks."""

    input_ids: tuple[int, ...]
    target_ids: tuple[int, ...]
    valid_mask: tuple[bool, ...]
    loss_mask: tuple[bool, ...]
    stream_start: int


@dataclass(frozen=True, slots=True)
class PackedBatch:
    """A rectangular group of packed examples ready for tensor conversion."""

    input_ids: tuple[tuple[int, ...], ...]
    target_ids: tuple[tuple[int, ...], ...]
    valid_mask: tuple[tuple[bool, ...], ...]
    loss_mask: tuple[tuple[bool, ...], ...]
    stream_starts: tuple[int, ...]


def _padded(values: Sequence[int], width: int, pad_id: int) -> tuple[int, ...]:
    return tuple((*values[:width], *(pad_id for _ in range(width - len(values)))))


def _padded_mask(values: Sequence[bool], width: int) -> tuple[bool, ...]:
    return tuple((*values[:width], *(False for _ in range(width - len(values)))))


def pack_causal_examples(
    documents: Iterable[Sequence[int]],
    *,
    eos_id: int,
    pad_id: int,
    context_length: int,
    stride: int | None = None,
) -> list[PackedExample]:
    """Pack documents while masking targets that cross an EOS boundary.

    The stream contains ``document + EOS`` for every document. The target
    immediately after an EOS is retained in the packed stream but receives a
    false loss mask, so the model is not trained to predict an unrelated
    document continuation. EOS itself remains a valid target.
    """

    if context_length < 1:
        raise ValueError("context_length must be positive")
    if stride is None:
        stride = context_length
    if stride < 1:
        raise ValueError("stride must be positive")

    stream: list[int] = []
    target_allowed: list[bool] = []
    for document in documents:
        tokens = list(document)
        if not tokens:
            continue
        stream.extend(tokens)
        target_allowed.extend([False, *(True for _ in tokens[1:])])
        stream.append(eos_id)
        target_allowed.append(True)
    if len(stream) < 2:
        return []

    starts = list(range(0, len(stream) - 1, stride))
    examples = []
    for start in starts:
        inputs = stream[start : start + context_length]
        targets = stream[start + 1 : start + context_length + 1]
        allowed = target_allowed[start + 1 : start + context_length + 1]
        examples.append(
            PackedExample(
                input_ids=_padded(inputs, context_length, pad_id),
                target_ids=_padded(targets, context_length, pad_id),
                valid_mask=_padded_mask([True] * len(targets), context_length),
                loss_mask=_padded_mask(allowed, context_length),
                stream_start=start,
            )
        )
    return examples


def batch_packed_examples(
    examples: Iterable[PackedExample], batch_size: int
) -> list[PackedBatch]:
    """Group fixed-width examples without changing their masks or order."""

    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    examples = list(examples)
    batches = []
    for start in range(0, len(examples), batch_size):
        group = examples[start : start + batch_size]
        batches.append(
            PackedBatch(
                input_ids=tuple(example.input_ids for example in group),
                target_ids=tuple(example.target_ids for example in group),
                valid_mask=tuple(example.valid_mask for example in group),
                loss_mask=tuple(example.loss_mask for example in group),
                stream_starts=tuple(example.stream_start for example in group),
            )
        )
    return batches
