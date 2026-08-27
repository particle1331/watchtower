from pathlib import Path

import pytest

from proof_lm.tokenization import DEFAULT_SPECIAL_TOKENS, load_tokenizer_artifact
from proof_lm.tokenization.byte_bpe import train_byte_level_bpe

TEXTS = [
    "A proof verifier checks P -> Q before training consumes the example.",
    "Café robots read mathematical text: λx. x + 1.",
    "<|document|> <|theorem|> <|proof|> <|turn_start|>",
]


def test_byte_level_bpe_round_trips_unicode_and_registers_contract_tokens() -> None:
    artifact = train_byte_level_bpe(
        TEXTS,
        training_dataset_id="dataset-prooflm-mixed-smoke-v1",
        vocab_size=512,
        min_frequency=1,
    )
    manifest = artifact.manifest
    assert manifest.vocab_size == artifact.tokenizer.get_vocab_size(with_added_tokens=True)
    assert set(manifest.special_tokens) == set(DEFAULT_SPECIAL_TOKENS)
    assert len(set(manifest.special_tokens.values())) == len(DEFAULT_SPECIAL_TOKENS)
    assert artifact.decode(artifact.encode("Café λx. proof ✓")) == "Café λx. proof ✓"
    assert artifact.token_id("<|tool_call|>") in manifest.special_tokens.values()


def test_byte_level_bpe_is_serialized_with_a_verified_manifest(tmp_path: Path) -> None:
    artifact = train_byte_level_bpe(
        TEXTS,
        training_dataset_id="dataset-prooflm-mixed-smoke-v1",
        vocab_size=512,
        min_frequency=1,
    )
    tokenizer_path, manifest_path = artifact.save(tmp_path / "tokenizer")
    assert tokenizer_path.exists()
    assert manifest_path.exists()

    loaded = load_tokenizer_artifact(tmp_path / "tokenizer")
    assert loaded.manifest == artifact.manifest
    assert loaded.encode("Café λx. proof ✓") == artifact.encode("Café λx. proof ✓")

    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            artifact.manifest.tokenizer_sha256,
            "0" * 64,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="hash"):
        load_tokenizer_artifact(tmp_path / "tokenizer")
