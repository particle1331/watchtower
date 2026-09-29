from __future__ import annotations

import json

from agent_harness.eval import (
    EvalTask,
    Judge,
    Scorecard,
    TaskSuite,
    Trajectory,
    TrajectoryStore,
)


def test_suite_and_trajectory_store_round_trip(tmp_path):
    task = EvalTask("task-1", "say hello", expected_text="hello")
    suite = TaskSuite("smoke", [task])
    suite_path = suite.save(tmp_path / "suite.json")
    restored_suite = TaskSuite.load(suite_path)

    trajectory = Trajectory.from_events(
        task.id,
        [
            {"type": "text_complete", "data": {"content": "hello"}},
            {"type": "agent_end", "data": {"response": "hello"}},
        ],
    )
    store = TrajectoryStore(tmp_path / "trajectories")
    trajectory_path = store.save(trajectory)
    restored_trajectory = store.load(task.id)

    assert restored_suite.task_ids == [task.id]
    assert store.list_ids() == [task.id]
    assert restored_trajectory.to_dict() == trajectory.to_dict()
    assert json.loads(trajectory_path.read_text())["task_id"] == task.id


def test_judge_and_scorecard_are_deterministic_and_serializable(tmp_path):
    tasks = [
        EvalTask("pass", "say hello", expected_text="hello", category="basic"),
        EvalTask("fail", "say hello", expected_text="hello", category="basic"),
    ]
    trajectories = [
        Trajectory("pass", response="hello", status="completed"),
        Trajectory("fail", response="goodbye", status="completed"),
    ]
    results = [
        Judge().evaluate(task, trajectory)
        for task, trajectory in zip(tasks, trajectories, strict=True)
    ]
    scorecard = Scorecard(results, suite="smoke", variant="full")

    path = scorecard.save(tmp_path / "scorecard.json")
    restored = Scorecard.load(path)

    assert scorecard.metrics["total_tasks"] == 2
    assert scorecard.metrics["passed_tasks"] == 1
    assert scorecard.by_category()["basic"]["total_tasks"] == 2
    assert restored.metrics == scorecard.metrics
    assert "Evaluation scorecard" in scorecard.to_markdown()
