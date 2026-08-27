"""Deterministic byte-level BPE training and manifest construction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tokenizers import AddedToken, Tokenizer
from tokenizers.decoders import ByteLevel as ByteLevelDecoder
from tokenizers.models import BPE
from tokenizers.pre_tokenizers import ByteLevel
from tokenizers.trainers import BpeTrainer

from ..identity import identity, sha256_digest
from ..schemas import TOKENIZER_SCHEMA, TokenizerManifest

DEFAULT_SPECIAL_TOKENS: tuple[str, ...] = (
    "<|pad|>",
    "<|unk|>",
    "<|bos|>",
    "<|eos|>",
    "<|document|>",
    "<|theorem|>",
    "<|proof|>",
    "<|system|>",
    "<|user|>",
    "<|assistant|>",
    "<|tool|>",
    "<|tool_call|>",
    "<|tool_result|>",
    "<|turn_start|>",
    "<|turn_end|>",
)


@dataclass(frozen=True, slots=True)
class TokenizerArtifact:
    """A byte-level tokenizer paired with the identity consumed by a run."""

    tokenizer: Tokenizer
    manifest: TokenizerManifest

    def encode(self, text: str, *, add_special_tokens: bool = False) -> list[int]:
        """Encode one string into IDs without silently changing its text."""

        encoding = self.tokenizer.encode(text, add_special_tokens=add_special_tokens)
        return encoding.ids

    def encode_batch(
        self, texts: list[str], *, add_special_tokens: bool = False
    ) -> list[list[int]]:
        """Encode a batch with the same explicit special-token policy."""

        encodings = self.tokenizer.encode_batch(texts, add_special_tokens=add_special_tokens)
        return [encoding.ids for encoding in encodings]

    def decode(self, ids: list[int], *, skip_special_tokens: bool = False) -> str:
        """Decode IDs using the serialized byte-level decoder."""

        return self.tokenizer.decode(ids, skip_special_tokens=skip_special_tokens)

    def token_id(self, token: str) -> int:
        """Return a registered token ID, failing loudly for an unknown name."""

        token_id = self.tokenizer.token_to_id(token)
        if token_id is None:
            raise KeyError(f"token is not registered: {token}")
        return token_id

    def save(self, directory: str | Path) -> tuple[Path, Path]:
        """Persist tokenizer JSON and its manifest under one artifact directory."""

        artifact_dir = Path(directory)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        tokenizer_path = artifact_dir / "tokenizer.json"
        manifest_path = artifact_dir / "manifest.json"
        payload = json.loads(self.tokenizer.to_str())
        tokenizer_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest_path.write_text(
            json.dumps(self.manifest.model_dump(mode="json"), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return tokenizer_path, manifest_path


def _special_tokens(
    names: tuple[str, ...],
) -> list[AddedToken]:
    return [
        AddedToken(name, single_word=False, lstrip=False, rstrip=False, normalized=False)
        for name in names
    ]


def _serialized_components(tokenizer: Tokenizer) -> dict[str, Any]:
    return json.loads(tokenizer.to_str())


def _manifest(
    tokenizer: Tokenizer,
    *,
    training_dataset_id: str,
    revision: str,
    normalizer_version: str,
    special_tokens: tuple[str, ...],
) -> TokenizerManifest:
    payload = _serialized_components(tokenizer)
    model = payload["model"]
    vocabulary = model["vocab"]
    merges = model.get("merges", [])
    token_ids = {
        token: tokenizer.token_to_id(token)
        for token in special_tokens
    }
    resolved_ids = {}
    for token, token_id in token_ids.items():
        if token_id is None:
            raise ValueError(f"trained tokenizer omitted special token: {token}")
        resolved_ids[token] = token_id
    tokenizer_sha256 = sha256_digest(payload)
    tokenizer_id = identity(
        "tok",
        {
            "dataset": training_dataset_id,
            "revision": revision,
            "tokenizer_sha256": tokenizer_sha256,
        },
    )
    return TokenizerManifest(
        schema_version=TOKENIZER_SCHEMA,
        tokenizer_id=tokenizer_id,
        revision=revision,
        vocab_size=tokenizer.get_vocab_size(with_added_tokens=True),
        vocabulary_sha256=sha256_digest(vocabulary),
        merges_sha256=sha256_digest(merges),
        normalizer_version=normalizer_version,
        special_tokens=resolved_ids,
        training_dataset_id=training_dataset_id,
        tokenizer_sha256=tokenizer_sha256,
    )


def train_byte_level_bpe(
    texts: list[str],
    *,
    training_dataset_id: str,
    vocab_size: int = 8192,
    min_frequency: int = 2,
    special_tokens: tuple[str, ...] = DEFAULT_SPECIAL_TOKENS,
    revision: str = "byte-bpe-v1",
    normalizer_version: str = "byte-level-identity-v1",
) -> TokenizerArtifact:
    """Train a byte-level BPE tokenizer on a checked, ordered text sample."""

    if not texts or any(not isinstance(text, str) for text in texts):
        raise ValueError("texts must be a non-empty list of strings")
    if vocab_size < len(special_tokens) + 256:
        raise ValueError("vocab_size must leave room for the byte alphabet and specials")
    if len(set(special_tokens)) != len(special_tokens):
        raise ValueError("special token names must be unique")
    if not training_dataset_id:
        raise ValueError("training_dataset_id must be non-empty")

    tokenizer = Tokenizer(BPE(unk_token="<|unk|>", byte_fallback=True))
    byte_level = ByteLevel(add_prefix_space=False)
    tokenizer.pre_tokenizer = byte_level
    tokenizer.decoder = ByteLevelDecoder()
    trainer = BpeTrainer(
        vocab_size=vocab_size,
        min_frequency=min_frequency,
        initial_alphabet=byte_level.alphabet(),
        special_tokens=_special_tokens(special_tokens),
        show_progress=False,
    )
    tokenizer.train_from_iterator(texts, trainer=trainer)
    manifest = _manifest(
        tokenizer,
        training_dataset_id=training_dataset_id,
        revision=revision,
        normalizer_version=normalizer_version,
        special_tokens=special_tokens,
    )
    return TokenizerArtifact(tokenizer=tokenizer, manifest=manifest)


def load_tokenizer_artifact(directory: str | Path) -> TokenizerArtifact:
    """Load and verify a tokenizer JSON/manifest pair."""

    artifact_dir = Path(directory)
    tokenizer_path = artifact_dir / "tokenizer.json"
    manifest_path = artifact_dir / "manifest.json"
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    manifest = TokenizerManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    actual_hash = sha256_digest(_serialized_components(tokenizer))
    if actual_hash != manifest.tokenizer_sha256:
        raise ValueError("tokenizer JSON hash does not match its manifest")
    if tokenizer.get_vocab_size(with_added_tokens=True) != manifest.vocab_size:
        raise ValueError("tokenizer vocabulary size does not match its manifest")
    for token, expected_id in manifest.special_tokens.items():
        if tokenizer.token_to_id(token) != expected_id:
            raise ValueError(f"special token ID mismatch for {token}")
    return TokenizerArtifact(tokenizer=tokenizer, manifest=manifest)
