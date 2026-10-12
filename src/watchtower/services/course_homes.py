"""Review and atomically move legacy course homes into CMS-managed contracts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import nbformat

from watchtower.course_home import legacy_home

from .content import CATALOG, ContentService, parse_state, validate_state, yaml_bytes
from .workspace import ServiceError, load_yaml, revision


class CourseHomeMigration:
    def __init__(self, root: Path):
        self.service = ContentService(root)

    def run(self, *, apply: bool = False, expected_revision: str | None = None) -> dict[str, Any]:
        store = self.service.store
        with store.locked():
            original = store.inputs()
            token = revision(original)
            if expected_revision is not None and expected_revision.strip('"') != token:
                raise ServiceError("stale workspace revision; review course-home migration again", code="conflict", status=412)
            state = parse_state(original)
            catalog = load_yaml(original[CATALOG] or b"", CATALOG)
            archive = f"archive/course-homes/{uuid4().hex}"
            writes: dict[str, bytes | None] = {}
            moves = []
            for artifact in state.artifacts:
                if artifact.kind != "course" or state.courses[artifact.id].home is not None:
                    continue
                name = f"backend/data/courses/{artifact.id.split('/')[-1]}.yaml"
                data = load_yaml(original[name] or b"", name)
                source = f"{artifact.path}/index.ipynb"
                value = original.get(source)
                if artifact.lifecycle != "planned" and value is None:
                    raise ServiceError("Started course is missing its legacy home; repair it before migrating.", paths=[source])
                data["home"] = {}
                if value is not None:
                    names = {Path(str(a.path)).stem for a in state.artifacts if a.parent == artifact.id}
                    data["home"] = legacy_home(nbformat.reads(value.decode(), as_version=4), artifact.title, names).model_dump()
                    writes[f"{archive}/{source}"] = value
                    writes[source] = None
                elif artifact.lifecycle != "planned":
                    raise ServiceError("Missing course-home content", paths=[source])
                record = next(a for a in catalog["artifacts"] if a["id"] == artifact.id)
                record["route"] = str(Path(record.get("route") or f"nb/courses/{artifact.id.split('/')[-1]}/index.ipynb").with_suffix(".qmd"))
                writes[name] = yaml_bytes(data)
                moves.append({"id": artifact.id, "source": source if value else None, "target": name,
                              "home": data["home"], "archive": f"{archive}/{source}" if value else None})
            report: dict[str, Any] = {"ready": True, "applied": False, "revision": token, "courses": moves}
            if not moves:
                return report
            writes[CATALOG] = yaml_bytes(catalog)
            writes[f"{archive}/record.json"] = json.dumps({"courses": moves, "preimages": {name: (original[name] or b"").decode() for name in writes if name.startswith("backend/data/")}}, indent=2).encode()
            candidate = {**original, **writes}
            validate_state(parse_state(candidate), candidate, store.root)
            if apply:
                transaction = store.commit(writes, original, "migrate course homes")
                report.update(applied=True, archive_path=archive, transaction=transaction, revision=revision(store.inputs()))
            return report
