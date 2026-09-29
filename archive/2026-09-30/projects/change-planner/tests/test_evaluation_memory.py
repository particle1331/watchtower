from typing import cast

from change_planner.evaluation import memory_scorecard


def test_memory_scorecard_covers_reuse_boundaries() -> None:
    rows = memory_scorecard()
    by_scenario = {row["scenario"]: row for row in rows}

    assert set(by_scenario) == {
        "no_memory",
        "valid_memory",
        "irrelevant_memory",
        "conflicting_memory",
        "stale_memory",
    }
    def metric(scenario: str, name: str) -> int:
        return cast(int, by_scenario[scenario][name])

    assert metric("valid_memory", "hits") >= 1
    assert metric("irrelevant_memory", "hits") == 0
    assert metric("conflicting_memory", "conflicts") >= 1
    assert metric("stale_memory", "hits") == 0
    assert metric("stale_memory", "invalidated") >= 1
