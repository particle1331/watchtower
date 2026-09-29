from typing import Any

from ml_platform.results import continuation


class _FakeStore:
    def __init__(self, children: list[dict[str, Any]]):
        self.children = children
        self.marks: list[tuple[str, str, dict[str, Any]]] = []
        self.finalize_calls: list[tuple[str, int]] = []

    def pending_children(self, parent_id: str, *, max_attempts: int) -> list[dict[str, Any]]:  # noqa: ARG002
        return [child.copy() for child in self.children if child["status"] in {"PENDING", "RETRY"} and child["attempts"] < max_attempts]

    def mark(self, run_id: str, status: str, **kwargs: Any) -> None:
        self.marks.append((run_id, status, kwargs))
        for child in self.children:
            if child["id"] == run_id:
                child["status"] = status
                if kwargs.get("increment_attempts"):
                    child["attempts"] += 1

    def finalize_parent(self, parent_id: str, *, max_attempts: int) -> str:
        self.finalize_calls.append((parent_id, max_attempts))
        return "SUCCESS" if all(child["status"] == "SUCCESS" for child in self.children) else "FAILURE"


def test_transient_failure_is_retried_until_success(monkeypatch) -> None:
    fake = _FakeStore([{"id": "child-1", "name": "one", "status": "PENDING", "attempts": 0}])
    monkeypatch.setattr(continuation, "store", fake)
    attempts = 0

    def process(_child: dict[str, Any]) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")

    assert continuation.run_until_done("parent", process, max_attempts=2) == "SUCCESS"
    assert attempts == 2
    assert [status for _, status, _ in fake.marks] == ["STARTED", "RETRY", "STARTED", "SUCCESS"]
    assert fake.finalize_calls == [("parent", 2)]


def test_exhausted_retry_finalizes_parent_as_failure(monkeypatch) -> None:
    fake = _FakeStore([{"id": "child-1", "name": "one", "status": "PENDING", "attempts": 0}])
    monkeypatch.setattr(continuation, "store", fake)

    def process(_child: dict[str, Any]) -> None:
        raise RuntimeError("permanent network outage")

    assert continuation.run_until_done("parent", process, max_attempts=2) == "FAILURE"
    assert len([status for _, status, _ in fake.marks if status == "RETRY"]) == 2
    assert fake.finalize_calls == [("parent", 2)]


def test_permanent_item_failure_is_not_retried(monkeypatch) -> None:
    fake = _FakeStore([{"id": "child-1", "name": "one", "status": "PENDING", "attempts": 0}])
    monkeypatch.setattr(continuation, "store", fake)

    def process(_child: dict[str, Any]) -> None:
        raise continuation.BatchItemFailure("bad input")

    assert continuation.run_until_done("parent", process) == "FAILURE"
    assert [status for _, status, _ in fake.marks] == ["STARTED", "FAILURE"]
