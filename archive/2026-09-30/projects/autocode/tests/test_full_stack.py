from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from autocode.application import AutocodeApplication
from autocode.domain import SessionRecord
from autocode.runner import DemoAgentRunner
from autocode.store.repository import SessionRepository
from autocode_service.api import create_app
from autocode_service.auth import TokenAuthority


def test_application_service_persists_the_agent_event_sequence(tmp_path):
    repository = SessionRepository(tmp_path / "sessions.db")
    application = AutocodeApplication(repository, DemoAgentRunner())
    session = application.create_session("vertical slice")

    async def collect():
        return [
            event
            async for event in application.stream_message(
                session.session_id, "explain the request path"
            )
        ]

    streamed = asyncio.run(collect())
    persisted = application.get_session(session.session_id).events

    assert [event.event_id for event in streamed] == [event.event_id for event in persisted]
    assert persisted[0].kind == "user_message"
    assert persisted[-1].kind == "run_finished"
    assert any(event.kind == "assistant_message" for event in persisted)


def test_browser_rest_websocket_and_sqlite_form_one_vertical_slice(tmp_path):
    app = create_app(
        database_path=tmp_path / "sessions.db",
        runner=DemoAgentRunner(),
        agent_mode="demo",
    )

    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="session-list"' in page.text
        assert 'src="/static/app.js"' in page.text
        assert client.get("/readyz").json()["ready"] is True

        created = client.post("/api/sessions", json={"title": "Browser run"})
        assert created.status_code == 201
        session_id = created.json()["session_id"]

        with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
            socket.send_json({"type": "user_message", "content": "trace this task"})
            events = []
            while not events or events[-1]["kind"] != "run_finished":
                events.append(socket.receive_json())

        assert events[0]["kind"] == "user_message"
        assert any(event["kind"] == "text_delta" for event in events)
        assert any(event["kind"] == "assistant_message" for event in events)
        assert [event["cursor"] for event in events] == list(range(1, len(events) + 1))

        restored = client.get(f"/api/sessions/{session_id}").json()
        assert [event["event_id"] for event in restored["events"]] == [
            event["event_id"] for event in events
        ]

        after_first = client.get(
            f"/api/sessions/{session_id}/events", params={"after": 1}
        ).json()
        assert [event["event_id"] for event in after_first] == [
            event["event_id"] for event in events[1:]
        ]
        hits = client.get("/api/search", params={"q": "trace task"}).json()
        assert any(hit["document_id"].startswith(f"session:{session_id}") for hit in hits)
        metrics = client.get("/metrics").text
        assert "sessions_created 1" in metrics
        assert "runs_started 1" in metrics


def test_websocket_cancel_is_a_durable_terminal_event(tmp_path):
    app = create_app(
        database_path=tmp_path / "sessions.db",
        runner=DemoAgentRunner(delay=0.2),
        agent_mode="demo",
    )

    with TestClient(app) as client:
        session_id = client.post("/api/sessions", json={"title": "Cancel run"}).json()[
            "session_id"
        ]
        with client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
            socket.send_json({"type": "user_message", "content": "long task"})
            assert socket.receive_json()["kind"] == "user_message"
            assert socket.receive_json()["kind"] == "run_started"
            socket.send_json({"type": "cancel"})
            terminal = socket.receive_json()

        assert terminal["kind"] == "run_finished"
        assert terminal["payload"]["reason"] == "cancelled"
        restored = client.get(f"/api/sessions/{session_id}").json()
        assert restored["events"][-1]["event_id"] == terminal["event_id"]


def test_unknown_session_is_rejected_at_both_transports(tmp_path):
    app = create_app(database_path=tmp_path / "sessions.db", runner=DemoAgentRunner())
    with TestClient(app) as client:
        assert client.get("/api/sessions/missing").status_code == 404
        try:
            with client.websocket_connect("/ws/sessions/missing"):
                raise AssertionError("missing session websocket unexpectedly connected")
        except Exception as exc:
            assert getattr(exc, "code", 4404) == 4404


def test_sync_routes_require_a_valid_device_token_and_are_idempotent(tmp_path):
    authority = TokenAuthority("test-secret")
    token = authority.issue("browser-test")
    app = create_app(
        database_path=tmp_path / "sessions.db",
        runner=DemoAgentRunner(),
        token_authority=authority,
    )
    record = SessionRecord("shared", title="Shared session")
    record.append("user_message", {"content": "from laptop"})
    payload = {"session": record.to_dict(), "idempotency_key": "browser-test:shared:1"}

    with TestClient(app) as client:
        assert client.post("/api/sync/sessions", json=payload).status_code == 401
        headers = {"Authorization": f"Bearer {token}"}
        first = client.post("/api/sync/sessions", json=payload, headers=headers)
        repeated = client.post("/api/sync/sessions", json=payload, headers=headers)
        pulled = client.get("/api/sync/sessions/shared/events", headers=headers)

    assert first.status_code == 200
    assert repeated.json() == first.json()
    assert [event["kind"] for event in pulled.json()] == ["user_message"]


def test_artifact_http_lifecycle_deduplicates_and_restores(tmp_path):
    app = create_app(database_path=tmp_path / "sessions.db", runner=DemoAgentRunner())
    with TestClient(app) as client:
        first = client.post(
            "/api/artifacts", content=b"patch contents", headers={"Content-Type": "text/plain"}
        )
        repeated = client.post(
            "/api/artifacts", content=b"patch contents", headers={"Content-Type": "text/plain"}
        )
        digest = first.json()["digest"]
        assert repeated.json()["digest"] == digest
        assert len(client.get("/api/artifacts").json()) == 1
        assert client.get(f"/api/artifacts/{digest}").content == b"patch contents"
        assert client.delete(f"/api/artifacts/{digest}").status_code == 204
        assert client.get(f"/api/artifacts/{digest}").status_code == 404
        assert client.post(f"/api/artifacts/{digest}/restore").status_code == 200
        assert client.get(f"/api/artifacts/{digest}").content == b"patch contents"
