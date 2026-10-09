"""Move managed storage without changing authored notebooks or public routes."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .content import CATALOG, parse_state, validate_state, yaml_bytes
from .workspace import ServiceError, WorkspaceStore, load_yaml, revision

LEGACY_ROOTS = ("content/data/", "content/assets/", "content/attachments/")


def managed_path(value: Any) -> Any:
    if isinstance(value, str) and value.startswith(LEGACY_ROOTS):
        return "backend/" + value.removeprefix("content/")
    return value


def relocate_record(name: str, value: bytes) -> bytes:
    """Only rewrite schema-owned paths; prose and unrelated fields stay intact."""
    if not name.startswith("content/data/") or not name.endswith((".yaml", ".yml")):
        return value
    data = load_yaml(value, name)
    changed = False
    groups = {
        "content/data/catalog.yaml": ("artifacts", ("path", "cover")),
        "content/data/portfolio.yaml": ("entries", ("figure_path",)),
        "content/data/photos.yaml": ("photos", ("path",)),
    }
    if name in groups:
        group, fields = groups[name]
        for record in data.get(group, []):
            if not isinstance(record, dict):
                raise ServiceError(f"{name}: expected {group} records", paths=[name])
            for field in fields:
                if field in record:
                    updated = managed_path(record[field])
                    changed |= updated != record[field]
                    record[field] = updated
    return yaml_bytes(data) if changed else value


class LayoutMigration:
    def __init__(self, root: Path):
        self.store = WorkspaceStore(root)

    def _candidate(self, original: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes | None]]:
        moves = [{"source": name, "target": managed_path(name)} for name, value in sorted(original.items()) if name.startswith(LEGACY_ROOTS) and value is not None]
        if original.get(CATALOG) is not None:
            if moves:
                raise ServiceError("both managed layouts exist; resolve legacy files explicitly before migrating", code="layout_conflict", status=409, paths=[item["source"] for item in moves])
            return {"migrated": False, "layout": "backend", "moves": [], "ready": True}, {}
        if original.get("content/data/catalog.yaml") is None:
            raise ServiceError("no content/data catalog to relocate; use wt migrate for legacy publishing inputs", paths=["content/data/catalog.yaml"])
        writes: dict[str, bytes | None] = {}
        for item in moves:
            source, target = item["source"], item["target"]
            if self.store.safe_path(target).exists():
                raise ServiceError("managed destination already exists; migration never overwrites it", code="layout_conflict", status=409, paths=[target])
            writes[target] = relocate_record(source, original[source] or b"")
            writes[source] = None
        candidate = {**original, **writes}
        validate_state(parse_state(candidate), candidate, self.store.root)
        return {"migrated": True, "layout": "backend", "moves": moves, "ready": True}, writes

    def run(self, *, apply: bool = False, expected_revision: str | None = None) -> dict[str, Any]:
        with self.store.locked():
            original = self.store.inputs()
            token = revision(original)
            if expected_revision is not None and expected_revision.strip('"') != token:
                raise ServiceError("stale workspace revision; re-read the migration before saving", code="conflict", status=412)
            report, writes = self._candidate(original)
            report.update(revision=token, applied=False)
            if apply and writes:
                transaction = self.store.commit(writes, original, "relocate managed storage")
                report.update(applied=True, transaction=transaction, revision=revision(self.store.inputs()))
            return report
