"""Revision-aware Kanban tasks with validated catalog links, shared by all clients."""
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from watchtower.models import KANBAN_COLUMNS, Kanban, KanbanCard, route_for, source_path
from watchtower.services.build import BuildService
from watchtower.services.content import KANBAN, ContentService, yaml_bytes
from watchtower.services.workspace import ServiceError, load_yaml


class KanbanService:
    def __init__(self, root: Path | None = None):
        self.content = ContentService(root)
        self.root = self.content.root

    @staticmethod
    def _board(files: Mapping[str, bytes | None]) -> Kanban:
        board = Kanban.model_validate(load_yaml(files[KANBAN] or b"", KANBAN)) if files.get(KANBAN) is not None else Kanban()
        # Give pre-reference cards permanent human-friendly identifiers. Once any
        # write occurs, these values and the counter are saved with the board.
        used = {int(card.ref.removeprefix("card#")) for card in board.cards if card.ref}
        number = max(board.next_number, max(used, default=0) + 1)
        for card in board.cards:
            if card.ref is None:
                while number in used:
                    number += 1
                card.ref = f"card#{number}"
                used.add(number)
                number += 1
        board.next_number = max(number, max(used, default=0) + 1)
        return board

    @staticmethod
    def _find_card(board: Kanban, identifier: str) -> int | None:
        return next((index for index, card in enumerate(board.cards) if identifier in {card.id, card.ref}), None)

    def read(self, column: str | None = None, query: str = "") -> dict[str, Any]:
        if column is not None and column not in dict(KANBAN_COLUMNS):
            raise ServiceError("Unknown Kanban column: " + column)
        snapshot = self.content.snapshot()
        artifacts = {a.id: a for a in snapshot.state.artifacts}
        build = BuildService(self.root).last_successful(mode="preview")
        base = ((build or {}).get("preview_url") or "http://127.0.0.1:4300").rstrip("/")
        cards = []
        board = self._board(snapshot.files)
        for card in board.cards:
            if column and card.column != column:
                continue
            if query.casefold() not in " ".join([card.title, card.description, *card.artifact_ids]).casefold():
                continue
            data = card.model_dump(mode="json")
            links = []
            for identifier in card.artifact_ids:
                artifact = artifacts[identifier]
                route = None if artifact.kind == "project" else route_for(artifact)
                source = artifact.path if artifact.kind in {"project", "gallery"} else source_path(artifact, snapshot.state)
                existing = bool(source and (snapshot.files.get(source) is not None or artifact.kind == "project" and (self.root / source).is_dir()))
                links.append({
                    "id": identifier, "title": artifact.title,
                    "cms_url": "/cms/artifact/" + quote(identifier, safe="/"),
                    "frontend_url": base + "/" + quote(str(PurePosixPath(route).with_suffix(".html")), safe="/") if route else None,
                    "source_path": str(self.root / source) if source else None,
                    "editor_url": "vscode://file/" + quote(str(self.root / str(source)), safe="/") if existing else None,
                })
            data["links"] = links
            cards.append(data)
        return {"cards": cards, "columns": [{"id": key, "title": title} for key, title in KANBAN_COLUMNS], "revision": snapshot.revision}

    def create(self, data: dict[str, Any], expected_revision: str | None = None) -> dict[str, Any]:
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            board = self._board(files)
            if "ref" in data:
                raise ServiceError("Kanban card references are assigned automatically")
            card = KanbanCard.model_validate({"id": uuid4().hex, **data, "ref": f"card#{board.next_number}"})
            if any(existing.id == card.id for existing in board.cards):
                raise ServiceError("Kanban card ID already exists: " + card.id)
            board.cards.append(card)
            board.next_number += 1
            return {"card": card.model_dump(mode="json")}, {KANBAN: yaml_bytes(board.model_dump(mode="json"))}
        return self.content._mutate("kanban create", apply, expected_revision)

    def update(self, card_id: str, patch: dict[str, Any], expected_revision: str | None = None) -> dict[str, Any]:
        if "id" in patch or "ref" in patch:
            raise ServiceError("Kanban card IDs and references cannot be changed")
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            board = self._board(files)
            index = self._find_card(board, card_id)
            if index is None:
                raise ServiceError("Unknown Kanban card: " + card_id, code="not_found", status=404)
            card = KanbanCard.model_validate({**board.cards[index].model_dump(mode="json"), **patch})
            board.cards[index] = card
            return {"card": card.model_dump(mode="json")}, {KANBAN: yaml_bytes(board.model_dump(mode="json"))}
        return self.content._mutate("kanban update", apply, expected_revision)

    def remove(self, card_id: str, expected_revision: str | None = None) -> dict[str, Any]:
        def apply(files: dict[str, bytes | None]) -> tuple[dict[str, Any], dict[str, bytes]]:
            board = self._board(files)
            index = self._find_card(board, card_id)
            if index is None:
                raise ServiceError("Unknown Kanban card: " + card_id, code="not_found", status=404)
            removed = board.cards.pop(index)
            return {"removed": removed.ref or removed.id}, {KANBAN: yaml_bytes(board.model_dump(mode="json"))}
        return self.content._mutate("kanban remove", apply, expected_revision)
