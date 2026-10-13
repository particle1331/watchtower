"""Consume temporary notebook starter inputs without keeping body fields in metadata."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from .workspace import ServiceError, load_yaml, revision

SEED_KINDS = frozenset({"post", "portfolio", "chapter"})
CHAPTER_METADATA = frozenset({"chapter_id", "section", "summary"})


def consume(catalog: dict[str, Any], original: dict[str, bytes | None], writes: dict[str, bytes],
            identifiers: set[str] | None = None) -> tuple[list[dict[str, Any]], str | None]:
    """Remove consumed starter payloads; archive their exact managed preimages.

    The caller owns the workspace lock and commits these writes with the notebook
    or migration. Planned entries are left alone. Chapter table metadata remains.
    """
    from .content import CATALOG, PORTFOLIO, yaml_bytes

    changes: list[dict[str, Any]] = []
    seeds: dict[str, Any] = {}
    preimages: set[str] = set()
    documents: dict[str, dict[str, Any]] = {}

    def document(name: str) -> dict[str, Any]:
        if name not in documents:
            documents[name] = load_yaml(writes.get(name) or original.get(name) or b"", name)
        return documents[name]

    for record in catalog["artifacts"]:
        identifier, kind = record["id"], record["kind"]
        if kind not in SEED_KINDS or record["lifecycle"] == "planned" or identifiers is not None and identifier not in identifiers:
            continue
        if kind == "post":
            if "planned" not in record:
                continue
            seed = record.pop("planned")
            name = CATALOG
        elif kind == "portfolio":
            name = PORTFOLIO
            detail = next(item for item in document(name)["entries"] if item["id"] == identifier)
            if "planned" not in detail:
                continue
            seed = detail.pop("planned")
        else:
            name = f"backend/data/courses/{record['parent'].split('/')[-1]}.yaml"
            row = next((item for item in document(name).get("planned", {}).get("chapters", []) if item["chapter_id"] == identifier), None)
            if row is None:
                continue
            seed = {key: row.pop(key) for key in list(row) if key not in CHAPTER_METADATA}
            if not seed:
                continue
        changes.append({"id": identifier, "kind": kind, "source": name, "fields": sorted(seed)})
        if seed:
            seeds[identifier] = seed
            preimages.add(name)

    if not changes:
        return [], None
    writes[CATALOG] = yaml_bytes(catalog)
    for name, data in documents.items():
        if any(change["source"] == name for change in changes):
            writes[name] = yaml_bytes(data)
    archive = f"archive/starter-seeds/{uuid4().hex}" if seeds else None
    if archive:
        writes[f"{archive}/record.json"] = json.dumps({"starter_seeds": seeds, "preimages": sorted(preimages)}, ensure_ascii=False, indent=2).encode()
        for name in preimages:
            if original.get(name) is not None:
                writes[f"{archive}/{name}"] = original[name] or b""
    return changes, archive


class StarterSeedMigration:
    """Review and recoverably clean starter payloads from already-started entries."""

    def __init__(self, root: Path):
        from .content import ContentService
        self.service = ContentService(root)

    def run(self, *, apply: bool = False, expected_revision: str | None = None) -> dict[str, Any]:
        from .content import CATALOG, parse_state, validate_state

        store = self.service.store
        with store.locked():
            original = store.inputs()
            token = revision(original)
            if expected_revision is not None and expected_revision.strip('"') != token:
                raise ServiceError("stale workspace revision; review starter-seed migration again", code="conflict", status=412)
            catalog = load_yaml(original[CATALOG] or b"", CATALOG)
            writes: dict[str, bytes] = {}
            changes, archive = consume(catalog, original, writes)
            report: dict[str, Any] = {"ready": True, "applied": False, "revision": token, "entries": changes}
            if not changes:
                return report
            candidate = {**original, **writes}
            validate_state(parse_state(candidate), candidate, store.root)
            if apply:
                transaction = store.commit({**writes}, original, "migrate consumed starter seeds")
                report.update(applied=True, archive_path=archive, transaction=transaction, revision=revision(store.inputs()))
            return report
