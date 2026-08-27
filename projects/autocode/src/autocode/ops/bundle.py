"""Consent-ready debug bundles with a single redaction pass."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from autocode.ops.logging import SecretScrubber


def create_debug_bundle(
    destination: str | Path,
    *,
    metadata: dict[str, object],
    logs: str,
    secrets: list[str] | tuple[str, ...] = (),
) -> Path:
    destination = Path(destination)
    scrubber = SecretScrubber(secrets)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("metadata.json", json.dumps(scrubber.scrub_mapping(metadata), indent=2))
        archive.writestr("logs.txt", scrubber.scrub(logs))
    return destination
