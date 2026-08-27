"""Dependency probes used by `/readyz` in a real service deployment."""

from __future__ import annotations


def health_report(*, database: bool = True, artifacts: bool = True) -> dict[str, object]:
    dependencies = {"database": database, "artifacts": artifacts}
    return {"ready": all(dependencies.values()), "dependencies": dependencies}
