"""Stable identities for configs and persisted ProofLM artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(value: Any) -> str:
    """Serialize a JSON-compatible value with a stable ordering."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def sha256_digest(value: Any) -> str:
    """Return the SHA-256 digest of a canonical JSON value."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def identity(prefix: str, value: Any) -> str:
    """Create a readable, content-addressed identity."""

    return f"{prefix}-{sha256_digest(value)[:16]}"
