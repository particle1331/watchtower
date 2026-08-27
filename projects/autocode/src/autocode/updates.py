"""Consent-gated update checks and explicit version comparison."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    notes_url: str
    digest: str = ""


def version_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.lstrip("v").split(".")[:3])


class UpdateChecker:
    def __init__(self, current: str, *, enabled: bool = False) -> None:
        self.current = current
        self.enabled = enabled

    def check(self, fetch: Callable[[], UpdateManifest]) -> UpdateManifest | None:
        if not self.enabled:
            return None
        manifest = fetch()
        return manifest if version_key(manifest.version) > version_key(self.current) else None
