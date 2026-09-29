from proof_lm.data import (
    batch_packed_examples,
    build_dataset_manifest,
    build_mixed_smoke_corpus,
    mixed_smoke_texts,
    pack_causal_examples,
    split_examples,
)
from proof_lm.logic import (
    atom,
    entails,
    find_countermodel,
    generate_examples,
    parse_formula,
    parse_proof,
    render_proof,
    verify_proof,
)
from proof_lm.logic.formula import implication


def test_formula_parser_renderer_and_semantics_round_trip() -> None:
    formula = parse_formula("P -> (Q & !R)")
    assert str(formula) == "P → Q ∧ ¬R"
    assert parse_formula(str(formula)) == formula
    assert formula.evaluate({"P": True, "Q": True, "R": False})
    assert not formula.evaluate({"P": True, "Q": False, "R": False})


def test_countermodel_is_checked_against_every_premise() -> None:
    p, q = atom("P"), atom("Q")
    countermodel = find_countermodel((implication(p, q),), q)
    assert countermodel == {"P": False, "Q": False}
    assert not entails((p,), q)


def test_generated_positive_proofs_verify_and_render_parse() -> None:
    examples = generate_examples(count=12, seed=17)
    positives = [example for example in examples if example.kind == "positive"]
    assert len(positives) == 12
    for example in positives:
        assert verify_proof(example.proof).valid
        assert verify_proof(parse_proof(render_proof(example.proof))).valid


def test_generated_negative_examples_are_checked_failures() -> None:
    examples = generate_examples(count=8, seed=17)
    negatives = [example for example in examples if example.kind == "negative"]
    assert negatives
    assert any(example.countermodel for example in negatives)
    assert all(not verify_proof(example.proof).valid for example in negatives)


def test_structural_split_keeps_every_group_on_one_side() -> None:
    examples = generate_examples(count=40, seed=3)
    splits = split_examples(examples, seed=17)
    split_by_id = {
        example_id: split for split, ids in splits.items() for example_id in ids
    }
    keys = {}
    for example in examples:
        keys.setdefault(example.structural_key, set()).add(split_by_id[example.example_id])
    assert all(len(split_names) == 1 for split_names in keys.values())
    assert set(split_by_id) == {example.example_id for example in examples}


def test_manifest_contains_provenance_structural_keys_and_checked_totals() -> None:
    examples = generate_examples(count=10)
    splits = split_examples(examples)
    manifest, records = build_dataset_manifest(examples, splits)
    assert manifest.total_examples == len(records)
    assert manifest.total_tokens > 0
    assert {"source_revision", "generator_version", "structural_key", "token_budget"} <= records[0].keys()
    assert sum(part.examples for part in manifest.splits.values()) == len(records)
    assert sum(part.token_count for part in manifest.splits.values()) == manifest.total_tokens


def test_mixed_smoke_corpus_preserves_sources_and_split_boundaries() -> None:
    manifest, records = build_mixed_smoke_corpus(seed=17, proof_count=12)
    assert manifest.dataset_manifest_id == "dataset-prooflm-mixed-smoke-v1"
    assert {str(row["source_kind"]) for row in records} == {
        "language",
        "mathematics",
        "generated-proof",
    }
    assert manifest.total_examples == len(records)
    assert sum(part.examples for part in manifest.splits.values()) == len(records)
    assert sum(part.token_count for part in manifest.splits.values()) == manifest.total_tokens

    split_by_hash: dict[str, set[str]] = {}
    split_by_structural_key: dict[str, set[str]] = {}
    for row in records:
        split = str(row["split"])
        split_by_hash.setdefault(str(row["sha256"]), set()).add(split)
        split_by_structural_key.setdefault(str(row["structural_key"]), set()).add(split)
    assert all(len(splits) == 1 for splits in split_by_hash.values())
    assert all(len(splits) == 1 for splits in split_by_structural_key.values())


def test_mixed_smoke_text_order_is_stable_for_downstream_tokenization() -> None:
    texts = mixed_smoke_texts(seed=17, proof_count=12)
    assert len(texts) == 40
    assert texts[0].startswith("A manifest records provenance")
    assert texts[-1]


def test_packed_causal_examples_shift_and_mask_document_boundaries() -> None:
    examples = pack_causal_examples(
        [[1, 2], [3, 4]], eos_id=9, pad_id=0, context_length=4, stride=4
    )
    assert examples[0].input_ids == (1, 2, 9, 3)
    assert examples[0].target_ids == (2, 9, 3, 4)
    assert examples[0].valid_mask == (True, True, True, True)
    assert examples[0].loss_mask == (True, True, False, True)
    assert examples[1].input_ids == (4, 9, 0, 0)
    assert examples[1].target_ids == (9, 0, 0, 0)
    assert examples[1].valid_mask == (True, False, False, False)
    assert examples[1].loss_mask == (True, False, False, False)

    batches = batch_packed_examples(examples, batch_size=1)
    assert len(batches) == 2
    assert batches[0].stream_starts == (0,)
    assert batches[1].stream_starts == (4,)
