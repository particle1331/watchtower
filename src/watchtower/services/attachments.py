"""Private, content-addressed context files owned by artifacts or Kanban cards.

Active references live with their owners. Archives are inert and may be pruned
manually; they are never consulted by reads, validation or reference counting.
"""
from __future__ import annotations

import io
import json
import mimetypes
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from watchtower.models import Attachment, Workspace
from watchtower.services.workspace import ServiceError, digest, load_yaml

MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
INLINE_IMAGES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


@dataclass(frozen=True)
class AttachmentUpload:
    name: str
    content: bytes


def describe(item: Attachment) -> dict[str, Any]:
    return {**item.model_dump(), "path": item.path, "download_url": f"/api/attachments/{item.id}", "image": item.media_type in INLINE_IMAGES}


def prepare(existing: list[dict[str, Any]], uploads: list[AttachmentUpload] | None = None, remove: list[str] | None = None) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
    removed = set(remove or [])
    if removed - {item["id"] for item in existing}:
        raise ServiceError("Attachment is no longer attached to this owner; reload before removing it.", code="conflict", status=412)
    items = {item["id"]: Attachment.model_validate(item).model_dump() for item in existing if item["id"] not in removed}
    writes = {}
    if len(uploads or []) > 20 or sum(len(upload.content) for upload in uploads or []) > 100 * 1024 * 1024:
        raise ServiceError("Attach at most 20 files and 100 MB at a time.")
    for upload in uploads or []:
        if not upload.content or len(upload.content) > MAX_ATTACHMENT_BYTES:
            raise ServiceError("Attachments must contain data and be at most 20 MB each.")
        name = upload.name.replace("\\", "/").rsplit("/", 1)[-1]
        media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if media_type in INLINE_IMAGES:
            try:
                with Image.open(io.BytesIO(upload.content)) as image:
                    image.verify()
                    media_type = Image.MIME.get(image.format or "", "application/octet-stream")
            except (UnidentifiedImageError, OSError, ValueError) as error:
                raise ServiceError("Cannot read attached image: " + name) from error
        item = Attachment(id=digest(upload.content), name=name, media_type=media_type, size=len(upload.content))
        items.setdefault(item.id, item.model_dump())
        writes[item.path] = upload.content
    return list(items.values()), writes


def references(state: Workspace) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for owner in [*state.artifacts, *state.kanban]:
        if len({item.id for item in owner.attachments}) != len(owner.attachments):
            raise ServiceError("Duplicate attachment references on " + owner.id)
        for item in owner.attachments:
            result.setdefault(item.id, []).append({"owner_id": owner.id, "owner_kind": getattr(owner, "kind", "kanban"), "owner_ref": getattr(owner, "ref", None), "owner_title": owner.title, "attachment": item.model_dump()})
    return result


def validate(state: Workspace, files: dict[str, bytes | None], *, missing_ok: bool = False) -> None:
    for identifier, owners in references(state).items():
        item = Attachment.model_validate(owners[0]["attachment"])
        value = files.get(item.path)
        if value is None and missing_ok:
            continue
        if value is None or digest(value) != identifier or any(owner["attachment"]["size"] != len(value) for owner in owners):
            raise ServiceError("Missing or changed context attachment: " + item.name, paths=[item.path])


def archive_unreferenced(after: Workspace, files: dict[str, bytes | None], writes: dict[str, bytes | None], result: dict[str, Any], operation: str) -> None:
    old: dict[str, list[dict[str, Any]]] = {}
    new = references(after)
    malformed_board = None
    for path, key in [("backend/data/catalog.yaml", "artifacts"), ("backend/data/kanban.yaml", "cards")]:
        value = files.get(path)
        if value is None or b"attachments:" not in value:
            continue
        try:
            records = load_yaml(value, path).get(key, [])
            for owner in records:
                for item in owner.get("attachments", []):
                    attachment = Attachment.model_validate(item)
                    old.setdefault(attachment.id, []).append({"owner_id": owner["id"], "owner_kind": owner.get("kind", "kanban"), "owner_ref": owner.get("ref"), "owner_title": owner["title"], "attachment": attachment.model_dump()})
        except (ValueError, KeyError, TypeError, AttributeError):
            if key != "cards" or operation not in {"update kanban", "batch"}:
                raise
            # Explicit board repair must remain possible. Preserve its damaged
            # bytes and archive only blobs with no reference in the repaired
            # workspace; never guess a former card identity or delete shared files.
            malformed_board = value
            for name, content in files.items():
                if not re.fullmatch(r"backend/attachments/[a-f0-9]{64}", name) or content is None:
                    continue
                identifier = name.rsplit("/", 1)[-1]
                if identifier not in new:
                    old.setdefault(identifier, []).append({"owner_id": None, "owner_kind": "unknown", "owner_title": "Malformed Kanban board", "attachment": {"id": identifier, "name": identifier, "media_type": "application/octet-stream", "size": len(content)}})
    lost = sorted(old.keys() - new.keys())
    if not lost:
        return
    archive = result.setdefault("archive_path", f"archive/deleted/{uuid4().hex}")
    # One archive per transaction, alongside existing entity-deletion records.
    metadata = {"operation": operation, "attachments": [owner for identifier in lost for owner in old[identifier]]}
    writes[f"{archive}/attachments.json"] = json.dumps(metadata, ensure_ascii=False, indent=2).encode()
    if malformed_board is not None:
        writes[f"{archive}/malformed-kanban.yaml"] = malformed_board
    for identifier in lost:
        path = f"backend/attachments/{identifier}"
        if files.get(path) is not None:
            writes[f"{archive}/{path}"] = files[path]
            writes[path] = None
    result["archived_attachments"] = lost


class AttachmentService:
    def __init__(self, root=None):
        from watchtower.services.content import ContentService
        self.content = ContentService(root)

    def read(self, owner: str | None = None) -> dict[str, Any]:
        snapshot = self.content.snapshot()
        records = [*snapshot.state.artifacts, *snapshot.state.kanban]
        target = next((record for record in records if owner in {record.id, getattr(record, "ref", None)}), None) if owner else None
        if owner and target is None:
            raise ServiceError("Unknown attachment owner: " + owner, status=404, code="not_found")
        refs = references(snapshot.state)
        items = target.attachments if target else [Attachment.model_validate(owners[0]["attachment"]) for owners in refs.values()]
        return {"owner": target.id if target else None, "attachments": [{**describe(item), "absolute_path": str(self.content.root / item.path), "owners": refs[item.id]} for item in items], "revision": snapshot.revision}

    def file(self, identifier: str) -> tuple[Attachment, bytes]:
        snapshot = self.content.snapshot()
        owners = references(snapshot.state).get(identifier)
        if not owners:
            raise ServiceError("Unknown attachment", status=404, code="not_found")
        item = Attachment.model_validate(owners[0]["attachment"])
        return item, snapshot.files[item.path]

    def change(self, owner: str, *, uploads: list[AttachmentUpload] | None = None, remove: list[str] | None = None, link: str | None = None, expected_revision: str | None = None) -> dict[str, Any]:
        from watchtower.services.content import CATALOG, KANBAN, parse_state, yaml_bytes
        def apply(files):
            state = parse_state(files)
            artifact = next((a for a in state.artifacts if a.id == owner), None)
            card = next((c for c in state.kanban if owner in {c.id, c.ref}), None)
            target = artifact or card
            if target is None:
                raise ServiceError("Unknown attachment owner: " + owner, status=404, code="not_found")
            items, writes = prepare([a.model_dump() for a in target.attachments], uploads, remove)
            if link:
                refs = references(state).get(link)
                if not refs:
                    raise ServiceError("Unknown attachment: " + link, status=404, code="not_found")
                if link not in {item["id"] for item in items}:
                    items.append(refs[0]["attachment"])
            if artifact:
                data = self.content._catalog(files)
                self.content._find(data, artifact.id)["attachments"] = items
                writes[CATALOG] = yaml_bytes(data)
            else:
                from watchtower.services.kanban import KanbanService
                board = KanbanService._board(files)
                saved = next(c for c in board.cards if c.id == target.id)
                saved.attachments = [Attachment.model_validate(a) for a in items]
                writes[KANBAN] = yaml_bytes(board.model_dump(mode="json"))
            return {"owner": target.id, "attachments": items}, writes
        return self.content._mutate("change attachments", apply, expected_revision)
