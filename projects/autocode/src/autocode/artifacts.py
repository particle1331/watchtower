"""Content-addressed artifact storage with a local S3-compatible seam."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactRef:
    digest: str
    size: int
    content_type: str = "application/octet-stream"
    tombstoned_at: float | None = None


class LocalArtifactStore:
    """Filesystem implementation of hash-addressed put/get semantics."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.objects = self.root / "objects"
        self.tombstones = self.root / "tombstones"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.tombstones.mkdir(parents=True, exist_ok=True)

    def put(self, content: bytes, content_type: str = "application/octet-stream") -> ArtifactRef:
        digest = hashlib.sha256(content).hexdigest()
        path = self.objects / digest
        if not path.exists():
            temporary = path.with_suffix(".part")
            temporary.write_bytes(content)
            os.replace(temporary, path)
        tombstone = self.tombstones / digest
        tombstone.unlink(missing_ok=True)
        return ArtifactRef(digest, len(content), content_type)

    def get(self, digest: str) -> bytes:
        if (self.tombstones / digest).exists():
            raise FileNotFoundError(f"artifact is tombstoned: {digest}")
        return (self.objects / digest).read_bytes()

    def delete(self, digest: str) -> None:
        if (self.objects / digest).exists():
            (self.tombstones / digest).write_text(str(time.time()), encoding="utf-8")

    def restore(self, digest: str) -> ArtifactRef:
        data = (self.objects / digest).read_bytes()
        (self.tombstones / digest).unlink(missing_ok=True)
        return ArtifactRef(digest, len(data))

    def list(self) -> list[ArtifactRef]:
        result: list[ArtifactRef] = []
        for path in sorted(self.objects.iterdir()):
            if path.is_file() and not (self.tombstones / path.name).exists():
                result.append(ArtifactRef(path.name, path.stat().st_size))
        return result

    def presigned_url(self, digest: str, *, expires_in: int = 300) -> str:
        """Return a local stand-in; an S3 adapter can preserve this interface."""
        if digest not in {ref.digest for ref in self.list()}:
            raise FileNotFoundError(digest)
        return f"file://{self.objects / digest}?expires={int(time.time()) + expires_in}"

    def write_manifest(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps([ref.__dict__ for ref in self.list()], indent=2), encoding="utf-8")
