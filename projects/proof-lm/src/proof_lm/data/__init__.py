"""Manifest and structural-split helpers for ProofLM datasets."""

from .batching import PackedBatch, PackedExample, batch_packed_examples, pack_causal_examples
from .manifest import (
    Document,
    build_dataset_manifest,
    build_mixed_smoke_corpus,
    content_hash,
    manifest_record,
    manifest_records,
    mixed_smoke_texts,
    normalize_text,
    split_examples,
)

__all__ = [
    "batch_packed_examples",
    "build_dataset_manifest",
    "build_mixed_smoke_corpus",
    "content_hash",
    "Document",
    "manifest_record",
    "manifest_records",
    "mixed_smoke_texts",
    "normalize_text",
    "PackedBatch",
    "PackedExample",
    "pack_causal_examples",
    "split_examples",
]
