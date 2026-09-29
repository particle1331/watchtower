from change_planner.baselines import compare_control_models


def test_control_comparison_makes_graph_tradeoffs_observable() -> None:
    rows = compare_control_models("retry-01")

    assert [row["approach"] for row in rows] == [
        "direct search",
        "staged Python planner",
        "LangGraph workflow",
    ]
    assert rows[0]["resumable"] is False
    assert rows[1]["resumable"] is False
    assert rows[2]["resumable"] is True
    assert rows[2]["parallel"] is True
    assert rows[2]["evidence_recall"] == 1.0
