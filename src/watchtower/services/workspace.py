"""Workspace locks, exact-byte revisions, and durable roll-forward transactions.

The advisory lock coordinates managed clients. Unmanaged IDE writes still have
a small check-to-replace race; observed divergences are always preserved.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

ABSENT = "absent"
_LOCKS: dict[str, threading.RLock] = {}
_LOCAL = threading.local()


class ServiceError(ValueError):
    def __init__(self, message: str, *, code: str = "validation", status: int = 422, paths: list[str] | None = None):
        super().__init__(message)
        self.code, self.status, self.paths = code, status, paths or []

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "paths": self.paths}


def digest(value: bytes | None) -> str:
    return ABSENT if value is None else hashlib.sha256(value).hexdigest()


def revision(files: dict[str, bytes | None]) -> str:
    return digest(json.dumps({p: digest(b) for p, b in sorted(files.items())}, sort_keys=True).encode())


def load_yaml(value: bytes, path: str) -> dict[str, Any]:
    parser = YAML(typ="safe")
    parser.allow_duplicate_keys = False
    try:
        result = parser.load(value.decode("utf-8"))
    except Exception as error:
        raise ServiceError(f"{path}: cannot parse YAML: {error}", paths=[path]) from error
    if not isinstance(result, dict):
        raise ServiceError(f"{path}: expected a mapping", paths=[path])
    if "version" in result and (type(result["version"]) is not int or result["version"] != 1):
        raise ServiceError(f"{path}: unsupported version (expected 1)", paths=[path])
    return result


def sync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def durable_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    sync_dir(path.parent)


class WorkspaceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.runtime = self.root / "backend/runtime"
        self.fault: Callable[[str, int], None] | None = None

    def safe_path(self, name: str) -> Path:
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or not name:
            raise ServiceError("expected repository-relative path", paths=[name])
        target = self.root / path
        if not target.resolve().is_relative_to(self.root):
            raise ServiceError("source symlink escapes workspace", paths=[name])
        return target

    def inputs(self) -> dict[str, bytes | None]:
        files: dict[str, bytes | None] = {}
        for prefix in ("content", "backend/data", "backend/assets", "backend/attachments", "frontend/templates", "frontend/assets"):
            base = self.root / prefix
            if base.exists():
                for path in sorted(base.rglob("*")):
                    if ".ipynb_checkpoints" in path.parts or "__pycache__" in path.parts:
                        continue
                    name = path.relative_to(self.root).as_posix()
                    self.safe_path(name)
                    if path.is_file():
                        files[name] = path.read_bytes()
        for name in ("backend/data/catalog.yaml", "backend/data/portfolio.yaml", "backend/data/photos.yaml", "backend/data/profile.yaml", "backend/data/kanban.yaml", "frontend/site.yaml"):
            path = self.safe_path(name)
            files[name] = path.read_bytes() if path.exists() else None
        # Directory identity is a dependency, but project code never enters a build snapshot.
        projects = self.root / "projects"
        archive = self.root / "archive"
        roots = [projects, *sorted(archive.glob("*/projects"))] if archive.exists() else [projects]
        for base in roots:
            if base.exists():
                for path in sorted(base.iterdir()):
                    if path.is_dir() or path.is_symlink():
                        name = path.relative_to(self.root).as_posix()
                        files[f"@dir/{name}"] = str(path.resolve()).encode()
        return files

    @contextmanager
    def locked(self) -> Iterator[None]:
        key = str(self.root)
        guard = _LOCKS.setdefault(key, threading.RLock())
        guard.acquire()
        depths = getattr(_LOCAL, "depths", {})
        _LOCAL.depths = depths
        if depths.get(key, 0):
            depths[key] += 1
            try:
                yield
            finally:
                depths[key] -= 1
                guard.release()
            return
        self.runtime.mkdir(parents=True, exist_ok=True)
        with (self.runtime / "workspace.lock").open("a+b") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            depths[key] = 1
            try:
                self.recover()
                yield
            finally:
                depths.pop(key, None)
                fcntl.flock(stream, fcntl.LOCK_UN)
                guard.release()

    def _manifest(self, directory: Path, data: dict[str, Any]) -> None:
        staging = directory / "manifest.next"
        durable_write(staging, json.dumps(data, sort_keys=True, indent=2).encode())
        os.replace(staging, directory / "manifest.json")
        sync_dir(directory)

    def _hash_at(self, name: str) -> str:
        path = self.safe_path(name)
        return digest(path.read_bytes() if path.exists() else None)

    def _install(self, name: str, value: bytes | None, expected: str, transaction: str) -> None:
        path = self.safe_path(name)
        if self._hash_at(name) != expected:
            raise ServiceError("destination changed during transaction", code="conflict", status=412, paths=[name])
        if value is None:
            path.unlink(missing_ok=True)
            sync_dir(path.parent)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.parent / f".wt-{transaction}-{uuid.uuid4().hex}"
        durable_write(staged, value)
        try:
            if self._hash_at(name) != expected:
                raise ServiceError("destination changed before installation", code="conflict", status=412, paths=[name])
            if expected == ABSENT:
                try:
                    os.link(staged, path)
                except FileExistsError as error:
                    raise ServiceError("reserved source was created externally", code="conflict", status=412, paths=[name]) from error
            else:
                os.replace(staged, path)
            sync_dir(path.parent)
        finally:
            staged.unlink(missing_ok=True)

    def _dependencies(self, manifest: dict[str, Any]) -> None:
        current = {name: digest(value) for name, value in self.inputs().items()}
        written = {item["path"] for item in manifest["writes"]}
        created = manifest.get("created_directories", {}) if manifest["status"] == "committing" else {}
        written.update(created)
        expected = manifest["inputs"]
        changed = sorted(name for name in set(current) | set(expected) if name not in written and current.get(name, ABSENT) != expected.get(name, ABSENT))
        changed.extend(name for name, identity in created.items() if current.get(name, ABSENT) not in {ABSENT, identity})
        if changed:
            raise ServiceError("transaction recovery blocked by external changes; journal versions retained", code="recovery_conflict", status=409, paths=changed)

    def recover(self) -> None:
        base = self.runtime / "transactions"
        if not base.exists():
            return
        for directory in sorted(base.iterdir()):
            path = directory / "manifest.json"
            if not path.exists():
                continue
            manifest = json.loads(path.read_bytes())
            if manifest["status"] in {"committed", "abandoned"}:
                self._clean_attachment_versions(directory, manifest)
                continue
            if manifest["status"] == "prepared":
                manifest["status"] = "abandoned"
                self._manifest(directory, manifest)
                self._clean_attachment_versions(directory, manifest)
                continue
            self._dependencies(manifest)
            for index, item in enumerate(manifest["writes"]):
                actual = self._hash_at(item["path"])
                if actual != item["candidate"]:
                    if actual != item["preimage"]:
                        raise ServiceError(f"transaction {directory.name} blocked: external edit; current, preimage, and candidate retained", code="recovery_conflict", status=409, paths=[item["path"]])
                    value = None if item["candidate"] == ABSENT else (directory / f"candidate-{index}").read_bytes()
                    if digest(value) != item["candidate"]:
                        raise ServiceError("damaged transaction candidate", code="recovery_conflict", status=409, paths=[str(directory)])
                    self._install(item["path"], value, item["preimage"], directory.name)
                manifest["progress"] = index + 1
                self._manifest(directory, manifest)
            self._dependencies(manifest)
            if any(self._hash_at(item["path"]) != item["candidate"] for item in manifest["writes"]):
                raise ServiceError("transaction verification failed", code="recovery_conflict", status=409)
            manifest["status"] = "committed"
            self._manifest(directory, manifest)
            self._clean_attachment_versions(directory, manifest)

    @staticmethod
    def _clean_attachment_versions(directory: Path, manifest: dict[str, Any]) -> None:
        # Recovery needs these bytes only until completion. The active file or
        # deleted archive is the sole durable copy afterward; pruning an archive
        # must not leave hidden attachment copies in completed runtime journals.
        for index, item in enumerate(manifest["writes"]):
            if any(item["path"].startswith(prefix) or f"/{prefix}" in item["path"] for prefix in ("backend/attachments/", "content/attachments/")):
                for prefix in ("preimage", "candidate"):
                    (directory / f"{prefix}-{index}").unlink(missing_ok=True)

    def commit(self, writes: dict[str, bytes | None], expected: dict[str, bytes | None], operation: str) -> str:
        """Called under locked(), after the entire candidate has been validated."""
        current = self.inputs()
        changed = sorted(name for name in set(current) | set(expected) if digest(current.get(name)) != digest(expected.get(name)))
        for name in writes:
            self.safe_path(name)
            if self._hash_at(name) != digest(expected.get(name)) and name not in changed:
                changed.append(name)
        if changed:
            raise ServiceError("workspace changed before commit", code="conflict", status=412, paths=changed)
        transaction = uuid.uuid4().hex
        directory = self.runtime / "transactions" / transaction
        directory.mkdir(parents=True)
        sync_dir(directory.parent)
        created = {name: digest(identity) for name, identity in self.project_directories(writes).items() if expected.get(name) is None}
        manifest: dict[str, Any] = {"id": transaction, "operation": operation, "status": "prepared", "progress": 0, "inputs": {p: digest(b) for p, b in expected.items()}, "writes": [], "created_directories": created}
        for index, (name, value) in enumerate(writes.items()):
            original = expected.get(name)
            if original is not None:
                durable_write(directory / f"preimage-{index}", original)
            if value is not None:
                durable_write(directory / f"candidate-{index}", value)
            manifest["writes"].append({"path": name, "exists": original is not None, "preimage": digest(original), "candidate": digest(value)})
        self._manifest(directory, manifest)
        if self.fault:
            self.fault("prepared", -1)
        self._dependencies(manifest)
        for item in manifest["writes"]:
            if self._hash_at(item["path"]) != item["preimage"]:
                raise ServiceError("destination changed before commit intent", code="conflict", status=412, paths=[item["path"]])
        manifest["status"] = "committing"
        self._manifest(directory, manifest)
        try:
            for index, (name, value) in enumerate(writes.items()):
                self._install(name, value, digest(expected.get(name)), transaction)
                if self.fault:
                    self.fault("installed", index)
                manifest["progress"] = index + 1
                self._manifest(directory, manifest)
                if self.fault:
                    self.fault("recorded", index)
            self._dependencies(manifest)
            for item in manifest["writes"]:
                if self._hash_at(item["path"]) != item["candidate"]:
                    raise ServiceError("result changed before verification", code="conflict", status=412, paths=[item["path"]])
            manifest["status"] = "committed"
            self._manifest(directory, manifest)
            self._clean_attachment_versions(directory, manifest)
        except Exception as error:
            raise ServiceError(f"transaction {transaction} pending recovery: {error}", code="pending_transaction", status=409, paths=[str(directory.relative_to(self.root))]) from error
        return transaction

    def project_directories(self, writes: dict[str, bytes | None]) -> dict[str, bytes]:
        """Project code stays out of snapshots; project identity remains a dependency."""
        result = {}
        for name in writes:
            parts = Path(name).parts
            if len(parts) > 2 and parts[0] == "projects":
                directory = f"projects/{parts[1]}"
                result[f"@dir/{directory}"] = str(self.safe_path(directory).resolve()).encode()
        return result
