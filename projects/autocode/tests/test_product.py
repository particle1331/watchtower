from __future__ import annotations

import zipfile

import pytest

from autocode.artifacts import LocalArtifactStore
from autocode.domain import SessionRecord
from autocode.jobs import JobQueue, JobStatus
from autocode.ops.bundle import create_debug_bundle
from autocode.ops.logging import SecretScrubber
from autocode.ops.metrics import Metrics
from autocode.realtime import FanoutHub, ReplayLog
from autocode.search.index import LocalSearchIndex
from autocode.state import UIState, reduce
from autocode.store.repository import SessionRepository
from autocode.sync.client import InMemorySyncServer, SyncClient
from autocode.sync.conflicts import merge_records
from autocode.updates import UpdateChecker, UpdateManifest
from autocode_service.auth import TokenAuthority
from autocode_service.deps import health_report


def test_repository_journals_and_replays_idempotently(tmp_path):
    repository = SessionRepository(tmp_path / "sessions.db")
    session = repository.create("demo")
    first = repository.append(session.session_id, "user_message", {"content": "hello"}, idempotency_key="a")
    second = repository.append(session.session_id, "user_message", {"content": "hello"}, idempotency_key="a")
    assert first.event_id == second.event_id
    loaded = repository.get(session.session_id)
    assert loaded is not None
    assert [event.kind for event in loaded.events] == ["user_message"]
    assert repository.journal.read()[0]["event"]["event_id"] == first.event_id


def test_repository_recovery_is_idempotent(tmp_path):
    repository = SessionRepository(tmp_path / "sessions.db")
    session = repository.create("recovery")
    event = repository.append(session.session_id, "user_message", {"content": "hello"})
    with repository._connect() as connection:
        connection.execute("DELETE FROM events WHERE event_id = ?", (event.event_id,))
        connection.execute("UPDATE sessions SET version = 0 WHERE session_id = ?", (session.session_id,))
    assert repository.recover() == 1
    assert repository.recover() == 0
    restored = repository.get(session.session_id)
    assert restored is not None
    assert restored.version == 1


def test_artifacts_deduplicate_and_tombstone(tmp_path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    one = store.put(b"same")
    two = store.put(b"same")
    assert one == two
    assert len(store.list()) == 1
    store.delete(one.digest)
    assert store.list() == []
    with pytest.raises(FileNotFoundError):
        store.get(one.digest)
    store.restore(one.digest)
    assert store.get(one.digest) == b"same"


def test_hybrid_search_is_deterministic_and_detects_staleness():
    index = LocalSearchIndex()
    index.add("cli.py", "def run_session(message):\n    return message\n")
    assert index.search("run session")[0].document_id == "cli.py#0"
    assert index.snapshot() == index.snapshot()
    assert index.freshness("cli.py", "def run_session(message):\n    return message\n") == "fresh"
    assert index.freshness("cli.py", "changed") == "stale"


def test_ui_reducer_ignores_duplicate_and_late_tool_events():
    state = reduce(UIState(), {"type": "tool_started", "call_id": "1", "name": "read"})
    state = reduce(state, {"type": "tool_started", "call_id": "1", "name": "read"})
    state = reduce(state, {"type": "tool_finished", "call_id": "1", "success": True, "output": "ok"})
    state = reduce(state, {"type": "tool_finished", "call_id": "1", "success": False, "error": "late"})
    assert len(state.cards) == 1
    assert state.cards[0].status == "done"


def test_concurrent_session_merges_converge():
    left = SessionRecord("s", updated_at="2026-01-01T00:00:00+00:00")
    right = SessionRecord("s", updated_at="2026-01-01T00:00:01+00:00")
    left.append("user_message", {"content": "left"})
    right.append("user_message", {"content": "right"})
    assert merge_records(merge_records(left, right), left).to_dict() == merge_records(left, right).to_dict()
    server = InMemorySyncServer()
    a = SyncClient("a", server)
    b = SyncClient("b", server)
    a.push(left)
    b.push(right)
    assert len(server.records["s"].events) == 2


def test_replay_log_and_slow_consumer_eviction():
    log = ReplayLog()
    log.publish("start", {})
    hub = FanoutHub(log, max_queue=1)
    queue = hub.subscribe("observer", after=1)
    hub.publish("one", {})
    hub.publish("two", {})
    assert "observer" not in hub.observers
    assert [event.cursor for event in log.since(1)] == [2, 3]
    assert queue.get_nowait().cursor == 2


def test_jobs_resume_and_dead_letter():
    queue = JobQueue(max_attempts=2)
    queue.enqueue("index", "reindex", {})
    attempts = iter([RuntimeError("crash"), 7])

    def worker(job):
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    assert queue.run("index", worker).status == JobStatus.RETRY
    result = queue.run("index", worker)
    assert result.status == JobStatus.COMPLETE
    assert result.checkpoint == 7
    queue.enqueue("poison", "reindex", {})
    queue.run("poison", lambda job: (_ for _ in ()).throw(ValueError("bad payload")))
    queue.run("poison", lambda job: (_ for _ in ()).throw(ValueError("bad payload")))
    assert queue.jobs["poison"].status == JobStatus.DEAD


def test_updates_are_opt_in_and_ops_are_scrubbed(tmp_path):
    calls = []
    checker = UpdateChecker("0.1.0", enabled=False)
    assert checker.check(lambda: calls.append(1) or UpdateManifest("0.2.0", "notes")) is None
    assert calls == []
    assert UpdateChecker("0.1.0", enabled=True).check(lambda: UpdateManifest("0.2.0", "notes")) is not None
    assert SecretScrubber(["secret"]).scrub("secret in logs") == "[REDACTED] in logs"
    metrics = Metrics()
    metrics.inc("sync_events")
    metrics.set("queue_depth", 2)
    assert "sync_events 1" in metrics.prometheus()
    bundle = create_debug_bundle(tmp_path / "debug.zip", metadata={"token": "secret"}, logs="secret", secrets=["secret"])
    with zipfile.ZipFile(bundle) as archive:
        assert "secret" not in archive.read("logs.txt").decode()


def test_device_tokens_and_readiness():
    authority = TokenAuthority("secret")
    token = authority.issue("laptop")
    assert authority.verify(token)["device_id"] == "laptop"
    authority.revoke(token)
    with pytest.raises(PermissionError):
        authority.verify(token)
    assert health_report(database=True, artifacts=False)["ready"] is False
