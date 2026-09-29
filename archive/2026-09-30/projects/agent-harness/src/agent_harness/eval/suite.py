"""Task and trajectory data structures used by the offline evaluator.

The evaluator stores plain JSON rather than pickled Python objects.  This
makes trajectories useful for regression tests, replay, and inspection without
requiring the model client or the agent's original process to be available.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def _jsonable(value: Any) -> Any:
    """Convert common harness values into JSON-compatible values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, BaseModel):
        return _jsonable(value.model_dump(mode="json"))
    if is_dataclass(value):
        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _jsonable(value.to_dict())
    return str(value)


def _parse_datetime(value: Any) -> datetime | str | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return str(value)


class EvalTask:
    """A reproducible task specification for an agent evaluation.

    ``checks`` are intentionally untyped at this layer.  The judge supports
    small declarative checks and callables, while callers can keep richer
    rubric metadata alongside them.  ``task_id``/``instruction`` and
    ``repository``/``cwd`` are accepted as aliases for the shorter names.
    """

    def __init__(
        self,
        id: str | None = None,
        prompt: str | None = None,
        checks: Iterable[Any] | None = None,
        *,
        task_id: str | None = None,
        name: str | None = None,
        instruction: str | None = None,
        task: str | None = None,
        description: str | None = None,
        repo: str | Path | None = None,
        repository: str | Path | None = None,
        cwd: str | Path | None = None,
        expected: Any = None,
        rubric: Any = None,
        expected_files: Iterable[str | Path] | None = None,
        expected_text: str | None = None,
        expected_output: str | None = None,
        test_command: str | None = None,
        setup_commands: Iterable[str] | None = None,
        teardown_commands: Iterable[str] | None = None,
        timeout: float = 120.0,
        max_turns: int | None = None,
        category: str | None = None,
        tags: Iterable[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        resolved_id = id or task_id or name
        if not resolved_id:
            raise ValueError("EvalTask requires an id or task_id")
        resolved_prompt = prompt if prompt is not None else instruction or task or description
        if resolved_prompt is None:
            raise ValueError("EvalTask requires a prompt or instruction")

        self.id = str(resolved_id)
        self.prompt = resolved_prompt
        self.checks = list(checks or [])
        repository_value = repository or repo or cwd
        self.repo = Path(repository_value) if repository_value is not None else None
        self.expected = expected if expected is not None else rubric
        self.expected_files = [str(path) for path in (expected_files or [])]
        self.expected_text = expected_text if expected_text is not None else expected_output
        self.test_command = test_command
        self.setup_commands = list(setup_commands or [])
        self.teardown_commands = list(teardown_commands or [])
        self.timeout = timeout
        self.max_turns = max_turns
        self.category = category
        self.tags = list(tags or [])
        self.metadata = dict(metadata or {})

    @property
    def task_id(self) -> str:
        """Compatibility alias for :attr:`id`."""
        return self.id

    @task_id.setter
    def task_id(self, value: str) -> None:
        self.id = str(value)

    @property
    def instruction(self) -> str:
        """Compatibility alias for :attr:`prompt`."""
        return self.prompt

    @property
    def repository(self) -> Path | None:
        """Compatibility alias for :attr:`repo`."""
        return self.repo

    def to_dict(self) -> dict[str, Any]:
        """Return the portable task representation."""
        result: dict[str, Any] = {
            "id": self.id,
            "prompt": self.prompt,
            "checks": _jsonable(self.checks),
        }
        optional = {
            "repo": self.repo,
            "expected": self.expected,
            "expected_files": self.expected_files,
            "expected_text": self.expected_text,
            "test_command": self.test_command,
            "setup_commands": self.setup_commands,
            "teardown_commands": self.teardown_commands,
            "timeout": self.timeout,
            "max_turns": self.max_turns,
            "category": self.category,
            "tags": self.tags,
            "metadata": self.metadata,
        }
        result.update(
            {
                key: _jsonable(value)
                for key, value in optional.items()
                if value is not None and value != [] and value != {}
            }
        )
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvalTask:
        """Build a task from a JSON-compatible mapping."""
        known = {
            "id": data.get("id"),
            "task_id": data.get("task_id"),
            "name": data.get("name"),
            "prompt": data.get("prompt"),
            "instruction": data.get("instruction"),
            "description": data.get("description"),
            "task": data.get("task"),
            "checks": data.get("checks", data.get("criteria", [])),
            "repo": data.get("repo"),
            "repository": data.get("repository"),
            "cwd": data.get("cwd"),
            "expected": data.get("expected"),
            "rubric": data.get("rubric"),
            "expected_files": data.get("expected_files", []),
            "expected_text": data.get("expected_text"),
            "expected_output": data.get("expected_output"),
            "test_command": data.get("test_command"),
            "setup_commands": data.get("setup_commands", data.get("setup", [])),
            "teardown_commands": data.get("teardown_commands", data.get("teardown", [])),
            "timeout": data.get("timeout", data.get("timeout_sec", 120.0)),
            "max_turns": data.get("max_turns"),
            "category": data.get("category"),
            "tags": data.get("tags", []),
            "metadata": data.get("metadata", {}),
        }
        return cls(**known)

    def __repr__(self) -> str:
        return f"EvalTask(id={self.id!r}, prompt={self.prompt!r})"


class TaskSuite:
    """An ordered collection of unique :class:`EvalTask` objects."""

    def __init__(
        self,
        name: str | Iterable[EvalTask | dict[str, Any]] = "default",
        tasks: Iterable[EvalTask | dict[str, Any]] | None = None,
        *,
        suite_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if not isinstance(name, str) and tasks is None:
            tasks = name
            name = suite_id or "default"
        self.name = suite_id or str(name)
        self.metadata = dict(metadata or {})
        self.tasks: list[EvalTask] = []
        for task in tasks or []:
            self.add(task)

    @property
    def id(self) -> str:
        """Compatibility alias for the suite name."""
        return self.name

    @property
    def task_ids(self) -> list[str]:
        return [task.id for task in self.tasks]

    def add(self, task: EvalTask | dict[str, Any]) -> EvalTask:
        """Append a task, rejecting duplicate identifiers."""
        resolved = EvalTask.from_dict(task) if isinstance(task, dict) else task
        if resolved.id in self.task_ids:
            raise ValueError(f"Duplicate evaluation task id: {resolved.id}")
        self.tasks.append(resolved)
        return resolved

    add_task = add

    def get(self, task_id: str, default: EvalTask | None = None) -> EvalTask | None:
        """Return a task by id, or *default* when it is absent."""
        return next((task for task in self.tasks if task.id == task_id), default)

    def __getitem__(self, task_id_or_index: str | int) -> EvalTask:
        if isinstance(task_id_or_index, int):
            return self.tasks[task_id_or_index]
        task = self.get(task_id_or_index)
        if task is None:
            raise KeyError(task_id_or_index)
        return task

    def __iter__(self):
        return iter(self.tasks)

    def __len__(self) -> int:
        return len(self.tasks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tasks": [task.to_dict() for task in self.tasks],
            "metadata": _jsonable(self.metadata),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str | Path) -> Path:
        """Write the suite as JSON and return the resulting path."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_json() + "\n", encoding="utf-8")
        return destination

    write = save

    @classmethod
    def from_dict(cls, data: dict[str, Any] | list[dict[str, Any]]) -> TaskSuite:
        if isinstance(data, list):
            return cls(tasks=data)
        tasks = data.get("tasks", data.get("items", []))
        return cls(
            name=data.get("name", data.get("id", "default")),
            tasks=tasks,
            metadata=data.get("metadata"),
        )

    @classmethod
    def load(cls, path: str | Path) -> TaskSuite:
        source = Path(path)
        return cls.from_dict(json.loads(source.read_text(encoding="utf-8")))

    from_file = load
    from_json_file = load


EvalSuite = TaskSuite
EvaluationSuite = TaskSuite


class Trajectory:
    """A serializable record of one agent attempt at an evaluation task."""

    def __init__(
        self,
        task_id: str | None = None,
        events: Iterable[Any] | None = None,
        *,
        id: str | None = None,
        response: str | None = None,
        final_response: str | None = None,
        output: str | None = None,
        final_output: str | None = None,
        status: str = "unknown",
        error: str | None = None,
        started_at: datetime | str | None = None,
        finished_at: datetime | str | None = None,
        ended_at: datetime | str | None = None,
        usage: Any = None,
        metadata: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        resolved_id = task_id or id
        if not resolved_id:
            raise ValueError("Trajectory requires a task_id")
        self.task_id = str(resolved_id)
        self.events = list(events or [])
        response_value = response
        if response_value is None:
            response_value = final_response
        if response_value is None:
            response_value = output if output is not None else final_output
        self.response = response_value
        self.status = status
        self.error = error
        self.started_at = started_at
        self.finished_at = finished_at if finished_at is not None else ended_at
        self.usage = usage
        self.metadata = dict(metadata or {})
        self.metrics = dict(metrics or {})

    @property
    def id(self) -> str:
        return self.task_id

    @property
    def final_response(self) -> str | None:
        return self.response

    @final_response.setter
    def final_response(self, value: str | None) -> None:
        self.response = value

    @property
    def ended_at(self) -> datetime | str | None:
        return self.finished_at

    @property
    def duration_ms(self) -> float | None:
        if not isinstance(self.started_at, datetime) or not isinstance(self.finished_at, datetime):
            return self.metrics.get("duration_ms")
        return (self.finished_at - self.started_at).total_seconds() * 1000

    @property
    def turns(self) -> int:
        return int(self.metrics.get("turns", self.metadata.get("turns", 0)))

    @property
    def success(self) -> bool:
        if "success" in self.metadata:
            return bool(self.metadata["success"])
        if self.status.lower() in {"success", "passed", "complete", "completed"}:
            return not self.error
        return bool(self.response or self.events) and not self.error and self.status.lower() != "failed"

    @property
    def tool_call_count(self) -> int:
        return sum(
            1
            for event in self.events
            if _event_type(event) in {"tool_call_start", "tool_call_complete"}
        )

    @property
    def has_error(self) -> bool:
        return bool(self.error) or any(_event_type(event) == "agent_error" for event in self.events)

    def add_event(self, event: Any) -> None:
        self.events.append(event)
        event_type = _event_type(event)
        data = _event_data(event)
        if event_type == "agent_error" and self.error is None:
            self.error = str(data.get("error", "agent error"))
        if event_type == "text_complete" and self.response is None:
            self.response = data.get("content")
        if event_type == "agent_end":
            self.status = "completed"
            if self.response is None:
                self.response = data.get("response")

    record = add_event

    @classmethod
    def from_events(
        cls,
        task_id: str,
        events: Iterable[Any],
        *,
        response: str | None = None,
        status: str = "completed",
        metadata: dict[str, Any] | None = None,
    ) -> Trajectory:
        trajectory = cls(task_id, status=status, response=response, metadata=metadata)
        for event in events:
            trajectory.add_event(event)
        return trajectory

    def to_dict(self) -> dict[str, Any]:
        result = {
            "task_id": self.task_id,
            "events": _jsonable(self.events),
            "response": self.response,
            "status": self.status,
            "error": self.error,
            "started_at": _jsonable(self.started_at),
            "finished_at": _jsonable(self.finished_at),
            "usage": _jsonable(self.usage),
            "metadata": _jsonable(self.metadata),
            "metrics": _jsonable(self.metrics),
        }
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trajectory:
        return cls(
            task_id=data.get("task_id", data.get("id")),
            events=data.get("events", []),
            response=data.get("response", data.get("final_response")),
            output=data.get("output", data.get("final_output")),
            status=data.get("status", "unknown"),
            error=data.get("error"),
            started_at=_parse_datetime(data.get("started_at")),
            finished_at=_parse_datetime(data.get("finished_at", data.get("ended_at"))),
            usage=data.get("usage"),
            metadata=data.get("metadata"),
            metrics=data.get("metrics"),
        )


def _event_type(event: Any) -> str:
    value = event.get("type", "") if isinstance(event, dict) else getattr(event, "type", "")
    return getattr(value, "value", str(value))


def _event_data(event: Any) -> dict[str, Any]:
    data = event.get("data", event) if isinstance(event, dict) else getattr(event, "data", {})
    return data if isinstance(data, dict) else {}


class TrajectoryStore:
    """Persist trajectories as one JSON document per task attempt."""

    def __init__(self, directory: str | Path = ".trajectories", *, root: str | Path | None = None) -> None:
        self.directory = Path(root if root is not None else directory)

    def path_for(self, task_id: str) -> Path:
        safe_id = "".join(character if character.isalnum() or character in "-_." else "_" for character in task_id)
        return self.directory / f"{safe_id}.json"

    def save(
        self,
        trajectory: Trajectory | str,
        value: Trajectory | Iterable[Any] | None = None,
    ) -> Path:
        """Save a trajectory.

        The normal form is ``save(trajectory)``.  ``save(task_id, events)`` is
        accepted as a convenience for small offline fixtures.
        """
        if isinstance(trajectory, Trajectory):
            resolved = trajectory
        elif isinstance(value, Trajectory):
            resolved = value
        else:
            resolved = Trajectory(str(trajectory), events=value or [])
        destination = self.path_for(resolved.task_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(resolved.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return destination

    write = save

    def load(self, task_id: str) -> Trajectory:
        path = self.path_for(task_id)
        if not path.is_file():
            raise FileNotFoundError(f"Trajectory not found: {path}")
        return Trajectory.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def exists(self, task_id: str) -> bool:
        return self.path_for(task_id).is_file()

    def list_ids(self) -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted(path.stem for path in self.directory.glob("*.json"))

    list = list_ids

    def iter(self):
        for task_id in self.list_ids():
            yield self.load(task_id)

    def delete(self, task_id: str) -> bool:
        path = self.path_for(task_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True


# The task-oriented name reads naturally in client code and preserves the
# terminology used by the capstone plan.
TaskSpec = EvalTask


__all__ = [
    "EvalSuite",
    "EvalTask",
    "EvaluationSuite",
    "TaskSpec",
    "TaskSuite",
    "Trajectory",
    "TrajectoryStore",
]
