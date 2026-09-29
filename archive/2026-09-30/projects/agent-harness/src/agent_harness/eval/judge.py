"""Deterministic trajectory judging for agent evaluations.

The default judge does not call a model.  It evaluates task health, declared
expectations, and small rubric checks directly so a scorecard can run offline
and remain reproducible.  An optional model client can add a qualitative
criterion explicitly with ``use_llm=True``.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_harness.eval.suite import EvalTask, Trajectory, _event_data, _event_type, _jsonable


@dataclass
class CriterionResult:
    """Outcome of one independent evaluation criterion."""

    name: str
    passed: bool
    score: float | None = None
    reason: str = ""
    weight: float = 1.0
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.score is None:
            self.score = 1.0 if self.passed else 0.0
        self.score = max(0.0, min(1.0, float(self.score)))

    @property
    def success(self) -> bool:
        return self.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "score": self.score,
            "reason": self.reason,
            "weight": self.weight,
            "details": _jsonable(self.details),
        }


@dataclass
class JudgeResult:
    """Aggregate result for one task trajectory."""

    task_id: str
    passed: bool
    score: float
    criteria: list[CriterionResult] = field(default_factory=list)
    feedback: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float | None = None

    @property
    def id(self) -> str:
        return self.task_id

    @property
    def success(self) -> bool:
        return self.passed

    @property
    def failures(self) -> list[CriterionResult]:
        return [criterion for criterion in self.criteria if not criterion.passed]

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "task_id": self.task_id,
            "passed": self.passed,
            "success": self.passed,
            "score": self.score,
            "criteria": [criterion.to_dict() for criterion in self.criteria],
            "feedback": self.feedback,
            "metadata": _jsonable(self.metadata),
        }
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JudgeResult:
        criteria = [
            CriterionResult(
                name=str(item.get("name", "criterion")),
                passed=bool(item.get("passed", False)),
                score=item.get("score"),
                reason=str(item.get("reason", "")),
                weight=float(item.get("weight", 1.0)),
                details=item.get("details", {}),
            )
            for item in data.get("criteria", [])
        ]
        return cls(
            task_id=str(data.get("task_id", data.get("id", ""))),
            passed=bool(data.get("passed", data.get("success", False))),
            score=float(data.get("score", 0.0)),
            criteria=criteria,
            feedback=str(data.get("feedback", "")),
            metadata=data.get("metadata", {}),
            duration_ms=data.get("duration_ms"),
        )


Check = Callable[[EvalTask, Trajectory], Any]


class Judge:
    """Evaluate a trajectory against an :class:`EvalTask`.

    Checks can be strings, mappings, or callables.  The supported mapping
    forms are deliberately small: ``contains``, ``not_contains``, ``status``,
    ``event``, ``tool_called``, ``metadata``, and ``command``.  A task may also
    use ``expected_text``, ``expected_files``, or ``test_command`` as concise
    top-level expectations.
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        sandbox: Any | None = None,
        use_llm: bool = False,
        run_commands: bool = True,
    ) -> None:
        self.client = client
        self.sandbox = sandbox
        self.use_llm = use_llm
        self.run_commands = run_commands

    def evaluate(
        self,
        task: EvalTask | dict[str, Any] | Trajectory,
        trajectory: Trajectory | dict[str, Any] | EvalTask | None = None,
    ) -> JudgeResult:
        """Synchronously evaluate a task and trajectory.

        Both ``evaluate(task, trajectory)`` and ``evaluate(trajectory, task)``
        are accepted because trajectory-first call sites are common when
        replaying stored attempts.
        """
        task, trajectory = _coerce_task_trajectory(task, trajectory)
        criteria = self._deterministic_criteria(task, trajectory)
        return _aggregate_result(task, trajectory, criteria)

    async def judge(
        self,
        task: EvalTask | dict[str, Any] | Trajectory,
        trajectory: Trajectory | dict[str, Any] | EvalTask | None = None,
    ) -> JudgeResult:
        """Evaluate a trajectory, optionally adding an explicit LLM criterion."""
        task, trajectory = _coerce_task_trajectory(task, trajectory)
        criteria = self._deterministic_criteria(task, trajectory)
        result = _aggregate_result(task, trajectory, criteria)
        if self.client is not None and self.use_llm:
            client = self.client
            llm_criterion = await self._llm_criterion(client, task, trajectory)
            result.criteria.append(llm_criterion)
            result = _aggregate_result(task, trajectory, result.criteria)
        return result

    evaluate_async = judge

    async def __call__(
        self,
        task: EvalTask | dict[str, Any] | Trajectory,
        trajectory: Trajectory | dict[str, Any] | EvalTask | None = None,
    ) -> JudgeResult:
        return await self.judge(task, trajectory)

    def _deterministic_criteria(
        self,
        task: EvalTask,
        trajectory: Trajectory,
    ) -> list[CriterionResult]:
        criteria = [
            CriterionResult(
                name="trajectory_completed",
                passed=not trajectory.has_error and trajectory.success,
                reason=(
                    "trajectory completed without an agent error"
                    if not trajectory.has_error and trajectory.success
                    else trajectory.error or "trajectory did not complete successfully"
                ),
            )
        ]

        if task.expected_text is not None:
            criteria.append(
                self._contains_criterion(
                    "expected_text",
                    trajectory.response or "",
                    task.expected_text,
                )
            )

        if task.expected_files:
            criteria.append(self._expected_files_criterion(task))

        if task.test_command:
            criteria.append(self._command_criterion("test_command", task.test_command, task))

        expected = task.expected
        if isinstance(expected, str):
            criteria.append(self._contains_criterion("expected", trajectory.response or "", expected))
        elif isinstance(expected, dict):
            criteria.extend(self._mapping_expectations(task, trajectory, expected))

        criteria.extend(self._check(task, trajectory, check) for check in task.checks)
        return criteria

    def _mapping_expectations(
        self,
        task: EvalTask,
        trajectory: Trajectory,
        expected: dict[str, Any],
    ) -> list[CriterionResult]:
        results: list[CriterionResult] = []
        if "contains" in expected or "text" in expected:
            value = expected.get("contains", expected.get("text"))
            results.append(self._contains_criterion("expected_text", trajectory.response or "", str(value)))
        if "status" in expected:
            wanted = str(expected["status"]).lower()
            actual = trajectory.status.lower()
            results.append(
                CriterionResult(
                    "expected_status",
                    actual == wanted,
                    reason=f"expected {wanted!r}, got {actual!r}",
                )
            )
        if "files" in expected:
            expected_files = list(expected["files"] or [])
            original = task.expected_files
            task.expected_files = [str(path) for path in expected_files]
            results.append(self._expected_files_criterion(task))
            task.expected_files = original
        return results

    def _check(self, task: EvalTask, trajectory: Trajectory, check: Any) -> CriterionResult:
        if callable(check):
            try:
                value = check(task, trajectory)
            except TypeError:
                value = check(trajectory)
            except Exception as exc:  # noqa: BLE001 - a bad rubric is a failed criterion
                return CriterionResult("callable_check", False, reason=f"check raised: {exc}")
            return _criterion_from_value("callable_check", value)

        if isinstance(check, str):
            return self._contains_criterion("contains", trajectory.response or "", check)

        if not isinstance(check, dict):
            return CriterionResult("check", False, reason="unsupported check type")

        name = str(check.get("name", check.get("type", "check")))
        weight = float(check.get("weight", 1.0))
        kind = str(check.get("type", check.get("kind", ""))).lower()
        if "contains" in check or kind in {"contains", "response_contains", "text_contains"}:
            expected = check.get("contains", check.get("value", check.get("text", "")))
            result = self._contains_criterion(name, trajectory.response or "", str(expected))
            result.weight = weight
            return result
        if "not_contains" in check or kind in {"not_contains", "response_excludes"}:
            unwanted = str(check.get("not_contains", check.get("value", "")))
            passed = unwanted not in (trajectory.response or "")
            return CriterionResult(name, passed, reason=f"unexpected text {unwanted!r}", weight=weight)
        if "status" in check or kind == "status":
            wanted = str(check.get("status", check.get("value", ""))).lower()
            passed = trajectory.status.lower() == wanted
            return CriterionResult(name, passed, reason=f"expected {wanted!r}, got {trajectory.status!r}", weight=weight)
        if "event" in check or kind == "event":
            expected_event = str(check.get("event", check.get("value", "")))
            actual_events = [_event_type(event) for event in trajectory.events]
            passed = expected_event in actual_events
            return CriterionResult(name, passed, reason=f"event {expected_event!r} present={passed}", weight=weight)
        if "tool_called" in check or kind == "tool_called":
            expected_tool = str(check.get("tool_called", check.get("value", "")))
            actual_tools = {
                str(_event_data(event).get("name"))
                for event in trajectory.events
                if _event_type(event) in {"tool_call_start", "tool_call_complete"}
            }
            passed = expected_tool in actual_tools
            return CriterionResult(name, passed, reason=f"tool {expected_tool!r} present={passed}", weight=weight)
        if "metadata" in check or kind == "metadata":
            expected_metadata = check.get("metadata", {})
            actual = trajectory.metadata
            passed = all(actual.get(key) == value for key, value in expected_metadata.items())
            return CriterionResult(name, passed, reason="metadata matched" if passed else "metadata mismatch", weight=weight)
        if "command" in check or kind in {"command", "test"}:
            command = str(check.get("command", check.get("value", "")))
            return self._command_criterion(name, command, task, weight=weight, check=check)
        return CriterionResult(name, False, reason="unsupported check mapping", weight=weight)

    def _contains_criterion(self, name: str, actual: str, expected: str) -> CriterionResult:
        passed = expected in actual
        return CriterionResult(
            name,
            passed,
            reason=f"expected text {expected!r} {'found' if passed else 'not found'}",
        )

    def _expected_files_criterion(self, task: EvalTask) -> CriterionResult:
        root = (task.repo or Path.cwd()).expanduser().resolve()
        missing: list[str] = []
        for file_name in task.expected_files:
            path = Path(file_name)
            path = path if path.is_absolute() else root / path
            if not path.is_file():
                missing.append(str(file_name))
        return CriterionResult(
            "expected_files",
            not missing,
            reason="all expected files exist" if not missing else f"missing: {', '.join(missing)}",
            details={"missing": missing},
        )

    def _command_criterion(
        self,
        name: str,
        command: str,
        task: EvalTask,
        *,
        weight: float = 1.0,
        check: dict[str, Any] | None = None,
    ) -> CriterionResult:
        if not self.run_commands:
            return CriterionResult(name, False, reason="command checks are disabled", weight=weight)
        root = (task.repo or Path.cwd()).expanduser().resolve()
        timeout = float((check or {}).get("timeout", task.timeout))
        expected_exit = int((check or {}).get("expected_exit_code", 0))
        try:
            completed = subprocess.run(
                command,
                shell=True,
                cwd=root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CriterionResult(name, False, reason=f"command failed to run: {exc}", weight=weight)
        passed = completed.returncode == expected_exit
        expected_output = (check or {}).get("stdout_contains")
        if passed and expected_output is not None:
            passed = str(expected_output) in completed.stdout
        return CriterionResult(
            name,
            passed,
            reason=(
                f"exit code {completed.returncode}, expected {expected_exit}"
                if passed
                else f"exit code {completed.returncode}, expected {expected_exit}; {completed.stderr.strip()}"
            ),
            weight=weight,
            details={
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
        )

    async def _llm_criterion(
        self,
        client: Any,
        task: EvalTask,
        trajectory: Trajectory,
    ) -> CriterionResult:
        prompt = self.build_prompt(task, trajectory)
        try:
            text = ""
            async for event in client.chat_completion(
                [
                    {"role": "system", "content": "Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            ):
                if getattr(event, "text_delta", None) is not None:
                    text = event.text_delta.content
                if getattr(event, "error", None):
                    return CriterionResult("llm_judge", False, reason=str(event.error), weight=0.0)
            parsed = _parse_json_object(text)
            passed = bool(parsed.get("passed", False))
            score = float(parsed.get("score", 1.0 if passed else 0.0))
            return CriterionResult(
                "llm_judge",
                passed,
                score=score,
                reason=str(parsed.get("reason", "")),
                details=parsed,
            )
        except Exception as exc:  # noqa: BLE001 - optional judging must not hide deterministic results
            return CriterionResult("llm_judge", False, reason=f"LLM judge failed: {exc}", weight=0.0)

    @staticmethod
    def build_prompt(task: EvalTask, trajectory: Trajectory) -> str:
        """Build the stable prompt used by an optional qualitative judge."""
        return (
            "Evaluate the following coding-agent trajectory against the task. "
            "Return JSON with boolean 'passed', numeric 'score' from 0 to 1, "
            "and a concise 'reason'.\n\n"
            f"Task: {task.prompt}\n\n"
            f"Trajectory: {json.dumps(trajectory.to_dict(), ensure_ascii=False)}"
        )


def _coerce_task_trajectory(
    task: EvalTask | dict[str, Any] | Trajectory,
    trajectory: Trajectory | dict[str, Any] | EvalTask | None,
) -> tuple[EvalTask, Trajectory]:
    if isinstance(task, Trajectory):
        if isinstance(trajectory, EvalTask):
            return trajectory, task
        if isinstance(trajectory, dict):
            return EvalTask.from_dict(trajectory), task
        return EvalTask(task_id=task.task_id, prompt=""), task
    resolved_task = EvalTask.from_dict(task) if isinstance(task, dict) else task
    if trajectory is None:
        raise ValueError("A trajectory is required")
    resolved_trajectory = (
        Trajectory.from_dict(trajectory) if isinstance(trajectory, dict) else trajectory
    )
    if isinstance(resolved_trajectory, EvalTask):
        raise TypeError("Expected a Trajectory as the second argument")
    return resolved_task, resolved_trajectory


def _criterion_from_value(name: str, value: Any) -> CriterionResult:
    if isinstance(value, CriterionResult):
        return value
    if isinstance(value, tuple) and len(value) >= 1:
        passed = bool(value[0])
        reason = str(value[1]) if len(value) > 1 else ""
        return CriterionResult(name, passed, reason=reason)
    if isinstance(value, dict):
        return CriterionResult(
            name,
            bool(value.get("passed", value.get("success", False))),
            score=value.get("score"),
            reason=str(value.get("reason", "")),
            details=value,
        )
    return CriterionResult(name, bool(value), reason=str(value))


def _aggregate_result(
    task: EvalTask,
    trajectory: Trajectory,
    criteria: list[CriterionResult],
) -> JudgeResult:
    weight = sum(max(0.0, criterion.weight) for criterion in criteria)
    score = (
        sum(float(criterion.score or 0.0) * max(0.0, criterion.weight) for criterion in criteria) / weight
        if weight
        else 0.0
    )
    passed = all(criterion.passed for criterion in criteria)
    failures = [criterion.reason for criterion in criteria if not criterion.passed and criterion.reason]
    return JudgeResult(
        task_id=task.id,
        passed=passed,
        score=round(score, 6),
        criteria=criteria,
        feedback="; ".join(failures),
        metadata={
            "category": task.category,
            "turns": trajectory.turns,
            "tool_calls": trajectory.tool_call_count,
            **task.metadata,
        },
        duration_ms=trajectory.duration_ms,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("LLM judge response must be a JSON object")
    return value


def judge_trajectory(
    task: EvalTask | dict[str, Any],
    trajectory: Trajectory | dict[str, Any],
) -> JudgeResult:
    """Convenience wrapper around the deterministic :class:`Judge`."""
    return Judge().evaluate(task, trajectory)


EvalJudge = Judge


__all__ = [
    "Check",
    "CriterionResult",
    "EvalJudge",
    "Judge",
    "JudgeResult",
    "judge_trajectory",
]
