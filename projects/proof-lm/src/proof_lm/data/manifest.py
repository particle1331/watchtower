"""Canonical text identities, structural splits, and compact dataset manifests."""

from __future__ import annotations

import hashlib
import random
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from ..identity import sha256_digest
from ..logic.generator import GeneratedExample, generate_examples
from ..schemas import DATASET_SCHEMA, DatasetManifest, SplitManifest


@dataclass(frozen=True, slots=True)
class Document:
    """Small source-document record used by the chapter's provenance fixture."""

    document_id: str
    source: str
    provenance: str
    text: str


MIXED_DOCUMENTS: tuple[tuple[str, str, str, str], ...] = (
    (
        "language-00",
        "language",
        "course-text-v1",
        "A manifest records provenance, and a split is a contract.",
    ),
    (
        "language-01",
        "language",
        "course-text-v1",
        "A verifier checks each proof step before training consumes it.",
    ),
    (
        "mathematics-00",
        "mathematics",
        "course-math-v1",
        "If P implies Q and P is true, then Q is true.",
    ),
    (
        "mathematics-01",
        "mathematics",
        "course-math-v1",
        "The conjunction of P and Q entails P.",
    ),
)


def normalize_text(text: str) -> str:
    """Apply the named fixture normalization used by the first manifest."""

    return re.sub(r"\s+", " ", text.strip()).casefold()


def content_hash(text: str) -> str:
    """Hash canonical text rather than a surface-form spelling."""

    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def manifest_record(document: Document, split: str) -> dict[str, object]:
    """Build one document-level manifest row with stable provenance fields."""

    normalized = normalize_text(document.text)
    return {
        "document_id": document.document_id,
        "source": document.source,
        "provenance": document.provenance,
        "split": split,
        "sha256": content_hash(document.text),
        "size_bytes": len(document.text.encode("utf-8")),
        "characters": len(normalized),
        "whitespace_tokens": len(normalized.split()),
    }


def split_examples(
    examples: Iterable[GeneratedExample],
    seed: int = 17,
    train_fraction: float = 0.6,
    validation_fraction: float = 0.2,
) -> dict[str, set[str]]:
    """Assign whole structural groups to splits deterministically."""

    if not 0 < train_fraction < 1 or not 0 <= validation_fraction < 1:
        raise ValueError("split fractions must be between zero and one")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train and validation fractions must leave a test split")
    examples = list(examples)
    groups: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for example in examples:
        groups[example.structural_key].append(example.example_id)
    group_keys = list(groups)
    random.Random(seed).shuffle(group_keys)
    n_train = round(train_fraction * len(group_keys))
    n_validation = round(validation_fraction * len(group_keys))
    train_groups = group_keys[:n_train]
    validation_groups = group_keys[n_train : n_train + n_validation]
    test_groups = group_keys[n_train + n_validation :]
    return {
        "train": {example_id for key in train_groups for example_id in groups[key]},
        "validation": {example_id for key in validation_groups for example_id in groups[key]},
        "test": {example_id for key in test_groups for example_id in groups[key]},
    }


def manifest_records(
    examples: Iterable[GeneratedExample], splits: dict[str, set[str]]
) -> list[dict[str, object]]:
    """Create the row-level provenance consumed by later tokenization stages."""

    split_by_id = {
        example_id: split for split, ids in splits.items() for example_id in ids
    }
    records = []
    for example in examples:
        text = example.proof_text
        records.append(
            {
                "example_id": example.example_id,
                "kind": example.kind,
                "split": split_by_id[example.example_id],
                "source_revision": "generated-proof-fixture-v1",
                "license": "course-generated",
                "generator_version": "proof-generator-v1",
                "normalization_version": "unicode-casefold-v1",
                "sha256": content_hash(text),
                "characters": len(normalize_text(text)),
                "token_budget": len(text.encode("utf-8")),
                "theorem_family": example.theorem_family,
                "proof_shape": example.proof_shape,
                "proof_depth": example.proof_depth,
                "variable_family": example.variable_family,
                "paraphrase_template": example.paraphrase_template,
                "perturbation": example.perturbation,
                "tool_schema": example.tool_schema,
                "structural_key": sha256_digest(example.structural_key),
                "verified": example.kind == "positive"
                and not example.countermodel,
            }
        )
    return records


def build_dataset_manifest(
    examples: Iterable[GeneratedExample],
    splits: dict[str, set[str]],
    dataset_manifest_id: str = "dataset-prooflm-smoke-v1",
) -> tuple[DatasetManifest, list[dict[str, object]]]:
    """Build a versioned manifest and its inspectable row records."""

    records = manifest_records(examples, splits)
    by_split: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        by_split[str(record["split"])].append(record)
    split_manifests = {}
    for split, rows in by_split.items():
        split_manifests[split] = SplitManifest(
            examples=len(rows),
            token_count=sum(int(str(row["token_budget"])) for row in rows),
            structural_keys_sha256=sha256_digest(sorted(str(row["structural_key"]) for row in rows)),
        )
    dataset = DatasetManifest(
        schema_version=DATASET_SCHEMA,
        dataset_manifest_id=dataset_manifest_id,
        source_revision="generated-proof-fixture-v1",
        license="course-generated",
        generator_version="proof-generator-v1",
        normalization_version="unicode-casefold-v1",
        content_sha256=sha256_digest(sorted(str(row["sha256"]) for row in records)),
        splits=split_manifests,
        total_examples=len(records),
        total_tokens=sum(int(str(row["token_budget"])) for row in records),
    )
    return dataset, records


def _document_splits(
    documents: Iterable[Document], seed: int
) -> dict[str, set[str]]:
    """Assign whole canonical document groups to deterministic partitions."""

    groups: dict[str, list[str]] = defaultdict(list)
    for document in documents:
        groups[content_hash(document.text)].append(document.document_id)
    group_keys = list(groups)
    random.Random(seed).shuffle(group_keys)
    n_train = max(1, round(0.6 * len(group_keys)))
    n_validation = max(1, round(0.2 * len(group_keys)))
    if n_train + n_validation >= len(group_keys):
        n_validation = max(0, len(group_keys) - n_train - 1)
    assignments = (
        ("train", group_keys[:n_train]),
        ("validation", group_keys[n_train : n_train + n_validation]),
        ("test", group_keys[n_train + n_validation :]),
    )
    return {
        split: {document_id for key in keys for document_id in groups[key]}
        for split, keys in assignments
    }


def _document_manifest_records(
    documents: Iterable[Document], splits: dict[str, set[str]]
) -> list[dict[str, object]]:
    split_by_id = {
        document_id: split for split, ids in splits.items() for document_id in ids
    }
    records = []
    for document in documents:
        normalized = normalize_text(document.text)
        records.append(
            {
                "document_id": document.document_id,
                "kind": "document",
                "source_kind": document.source,
                "split": split_by_id[document.document_id],
                "source_revision": document.provenance,
                "license": "course-fixtures",
                "generator_version": "course-fixtures-v1",
                "normalization_version": "unicode-casefold-v1",
                "sha256": content_hash(document.text),
                "characters": len(normalized),
                "token_budget": len(document.text.encode("utf-8")),
                "structural_key": sha256_digest(
                    ("document", content_hash(document.text))
                ),
                "verified": False,
            }
        )
    return records


def build_mixed_smoke_corpus(
    seed: int = 17, proof_count: int = 12
) -> tuple[DatasetManifest, list[dict[str, object]]]:
    """Build the compact mixed corpus used by the course's smoke contract.

    The rows deliberately retain their source kind. Language and mathematics
    fixtures are split by canonical document hash; generated proofs are split
    by structural key. This keeps the teaching corpus small without hiding
    the boundary that a production data pipeline must enforce.
    """

    documents = [
        Document(document_id, source, provenance, text)
        for document_id, source, provenance, text in MIXED_DOCUMENTS
    ]
    document_splits = _document_splits(documents, seed=seed)
    proof_examples = generate_examples(count=proof_count, seed=seed)
    proof_splits = split_examples(proof_examples, seed=seed)
    records = _document_manifest_records(documents, document_splits)
    proof_records = manifest_records(proof_examples, proof_splits)
    for record in proof_records:
        record["source_kind"] = "generated-proof"
    records.extend(proof_records)

    by_split: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        by_split[str(record["split"])].append(record)
    split_manifests = {
        split: SplitManifest(
            examples=len(rows),
            token_count=sum(int(str(row["token_budget"])) for row in rows),
            structural_keys_sha256=sha256_digest(
                sorted(str(row["structural_key"]) for row in rows)
            ),
        )
        for split, rows in by_split.items()
    }
    dataset = DatasetManifest(
        schema_version=DATASET_SCHEMA,
        dataset_manifest_id="dataset-prooflm-mixed-smoke-v1",
        source_revision="mixed-smoke-fixture-v1",
        license="course-fixtures-and-generated",
        generator_version="course-fixtures-v1+proof-generator-v1",
        normalization_version="unicode-casefold-v1",
        content_sha256=sha256_digest(
            sorted(str(row["sha256"]) for row in records)
        ),
        splits=split_manifests,
        total_examples=len(records),
        total_tokens=sum(int(str(row["token_budget"])) for row in records),
    )
    return dataset, records


def mixed_smoke_texts(seed: int = 17, proof_count: int = 12) -> list[str]:
    """Return the ordered text sample paired with the mixed smoke manifest."""

    documents = [
        Document(document_id, source, provenance, text)
        for document_id, source, provenance, text in MIXED_DOCUMENTS
    ]
    proof_examples = generate_examples(count=proof_count, seed=seed)
    return [document.text for document in documents] + [
        example.proof_text for example in proof_examples
    ]
