"""Redact secrets before logs or support bundles leave the process."""

from __future__ import annotations

import re


class SecretScrubber:
    def __init__(self, secrets: list[str] | tuple[str, ...] = ()) -> None:
        escaped = [re.escape(secret) for secret in secrets if secret]
        self._pattern = re.compile("|".join(escaped)) if escaped else None

    def scrub(self, value: str) -> str:
        if self._pattern is None:
            return value
        return self._pattern.sub("[REDACTED]", value)

    def scrub_mapping(self, value: dict[str, object]) -> dict[str, object]:
        return {key: self.scrub(str(item)) if isinstance(item, str) else item for key, item in value.items()}
