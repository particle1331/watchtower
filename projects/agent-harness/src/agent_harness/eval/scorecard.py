"""Aggregation and reporting for evaluation results."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from statistics import mean
from typing import Any

from agent_harness.eval.judge import Judge, JudgeResult
from agent_harness.eval.suite import EvalTask, Trajectory, _jsonable


class Scorecard:
    """Summarize per-task :class:`JudgeResult` objects.

    A scorecard is intentionally a data/reporting object.  It does not run an
    agent or contact a model, which keeps variant comparisons and regression
    tests reproducible offline.
    """

    def __init__(
        self,
        results: Iterable[JudgeResult | dict[str, Any]] | str | None = None,
        *,
        suite: str = "default",
        suite_name: str | None = None,
        variant: str = "full",
        name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(results, str):
            suite = results
            results = None
        self.suite = suite_name or suite
        self.variant = variant
        self.name = name or self.suite
        self.metadata = dict(metadata or {})
        self.results: list[JudgeResult] = []
        for result in results or []:
            self.add(result)

    @property
    def suite_name(self) -> str:
        return self.suite

    @property
    def judgements(self) -> list[JudgeResult]:
        """Compatibility alias for :attr:`results`."""
        return self.results

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def total_tasks(self) -> int:
        return self.total

    @property
    def passed(self) -> int:
        return sum(result.passed for result in self.results)

    @property
    def passed_tasks(self) -> int:
        return self.passed

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def success_rate(self) -> float:
        return self.pass_rate

    @property
    def mean_score(self) -> float:
        return mean(result.score for result in self.results) if self.results else 0.0

    @property
    def average_score(self) -> float:
        return self.mean_score

    @property
    def score(self) -> float:
        return self.mean_score

    @property
    def metrics(self) -> dict[str, Any]:
        """Return aggregate metrics suitable for JSON or a comparison table."""
        scores = [result.score for result in self.results]
        durations = [
            result.duration_ms for result in self.results if result.duration_ms is not None
        ]
        turns = [_numeric_metadata(result, "turns") for result in self.results]
        tool_calls = [_numeric_metadata(result, "tool_calls") for result in self.results]
        return {
            "total_tasks": self.total,
            "passed_tasks": self.passed,
            "failed_tasks": self.failed,
            "pass_rate": round(self.pass_rate, 6),
            "success_rate": round(self.success_rate, 6),
            "mean_score": round(self.mean_score, 6),
            "average_score": round(self.average_score, 6),
            "min_score": round(min(scores), 6) if scores else 0.0,
            "max_score": round(max(scores), 6) if scores else 0.0,
            "mean_duration_ms": round(mean(durations), 3) if durations else 0.0,
            "mean_turns": round(mean(turns), 3) if turns else 0.0,
            "mean_tool_calls": round(mean(tool_calls), 3) if tool_calls else 0.0,
        }

    def add(self, result: JudgeResult | dict[str, Any]) -> JudgeResult:
        """Append one result and return it."""
        resolved = JudgeResult.from_dict(result) if isinstance(result, dict) else result
        self.results.append(resolved)
        return resolved

    add_result = add

    def by_task(self) -> dict[str, JudgeResult]:
        return {result.task_id: result for result in self.results}

    def by_category(self) -> dict[str, dict[str, Any]]:
        """Return the same aggregate metrics grouped by result category."""
        groups: dict[str, list[JudgeResult]] = defaultdict(list)
        for result in self.results:
            category = str(result.metadata.get("category") or "uncategorized")
            groups[category].append(result)
        return {
            category: Scorecard(
                values,
                suite=self.suite,
                variant=self.variant,
                name=f"{self.name}:{category}",
            ).metrics
            for category, values in sorted(groups.items())
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "suite": self.suite,
            "variant": self.variant,
            "metrics": self.metrics,
            "by_category": self.by_category(),
            "results": [result.to_dict() for result in self.results],
            "metadata": _jsonable(self.metadata),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save(self, path: str | Path) -> Path:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self.to_json() + "\n", encoding="utf-8")
        return destination

    write = save

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Scorecard:
        return cls(
            data.get("results", []),
            suite=data.get("suite", data.get("suite_name", "default")),
            variant=data.get("variant", "full"),
            name=data.get("name"),
            metadata=data.get("metadata"),
        )

    @classmethod
    def load(cls, path: str | Path) -> Scorecard:
        source = Path(path)
        return cls.from_dict(json.loads(source.read_text(encoding="utf-8")))

    from_file = load

    def to_markdown(self) -> str:
        """Render a compact human-readable scorecard."""
        metrics = self.metrics
        lines = [
            f"# Evaluation scorecard: {self.name}",
            "",
            f"- Suite: `{self.suite}`",
            f"- Variant: `{self.variant}`",
            f"- Tasks: {metrics['passed_tasks']}/{metrics['total_tasks']} passed",
            f"- Mean score: {metrics['mean_score']:.3f}",
            "",
            "| Task | Passed | Score | Feedback |",
            "| --- | ---: | ---: | --- |",
        ]
        for result in self.results:
            feedback = result.feedback.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| `{result.task_id}` | {'yes' if result.passed else 'no'} "
                f"| {result.score:.3f} | {feedback} |"
            )
        return "\n".join(lines) + "\n"

    markdown = to_markdown
    report = to_markdown

    @classmethod
    def from_trajectories(
        cls,
        tasks: Iterable[EvalTask | dict[str, Any]],
        trajectories: Iterable[Trajectory | dict[str, Any]],
        *,
        judge: Judge | None = None,
        suite: str = "default",
        variant: str = "full",
    ) -> Scorecard:
        """Judge matching task/trajectory pairs and aggregate the results."""
        resolved_judge = judge or Judge()
        task_by_id = {
            task.id if isinstance(task, EvalTask) else EvalTask.from_dict(task).id: task
            for task in tasks
        }
        results: list[JudgeResult] = []
        for value in trajectories:
            trajectory = value if isinstance(value, Trajectory) else Trajectory.from_dict(value)
            task = task_by_id.get(trajectory.task_id)
            if task is None:
                continue
            results.append(resolved_judge.evaluate(task, trajectory))
        return cls(results, suite=suite, variant=variant)

    @classmethod
    def compare(
        cls,
        scorecards: Mapping[str, Scorecard] | Iterable[Scorecard],
    ) -> dict[str, dict[str, Any]]:
        """Return comparable metric rows for full and ablated variants."""
        if isinstance(scorecards, Mapping):
            values = ((str(name), scorecard) for name, scorecard in scorecards.items())
        else:
            values = ((scorecard.variant, scorecard) for scorecard in scorecards)
        return {name: scorecard.metrics for name, scorecard in values}

    @classmethod
    def from_variants(
        cls,
        variants: Mapping[str, Iterable[JudgeResult | dict[str, Any]]],
        *,
        suite: str = "default",
    ) -> dict[str, Scorecard]:
        """Build one scorecard per ablation/variant name."""
        return {
            variant: cls(results, suite=suite, variant=variant)
            for variant, results in variants.items()
        }


def _numeric_metadata(result: JudgeResult, key: str) -> float:
    value = result.metadata.get(key, 0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_scorecard(
    results: Iterable[JudgeResult | dict[str, Any]],
    *,
    suite: str = "default",
    variant: str = "full",
) -> Scorecard:
    """Convenience function for callers that do not need a classmethod."""
    return Scorecard(results, suite=suite, variant=variant)


EvaluationScorecard = Scorecard
AblationScorecard = Scorecard


__all__ = [
    "AblationScorecard",
    "EvaluationScorecard",
    "Scorecard",
    "build_scorecard",
]
