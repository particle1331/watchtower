# pyright: reportTypedDictNotRequiredAccess=false

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from evidence_brief.fixtures import request_for
from evidence_brief.schemas import FaultPlan, ReviewDecision
from evidence_brief.workflow import build_evidence_brief_graph, make_context, run_fixture


def test_happy_path_is_complete_and_traceable() -> None:
    state = run_fixture("conflict-01")
    assert state["status"] == "complete"
    assert state["artifact"]["recommendation"] == "requires_exception_analysis"
    assert state["contradictions"]
    assert len({row["task_id"] for row in state["branch_results"]}) == 3
    assert len(state["artifact"]["citations"]) == len(state["claims"])
    assert state["run_metrics"]["effects"].count("export:artifact") == 1


def test_edit_changes_exported_recommendation() -> None:
    decision = ReviewDecision(
        action="edit",
        reason="narrow the recommendation",
        edited_recommendation="exception_not_established",
    )
    state = run_fixture("conflict-01", review_decision=decision)
    assert state["artifact"]["recommendation"] == "exception_not_established"
    assert "Exception not established" in state["artifact"]["markdown"]


def test_reject_then_approve_uses_bounded_revision() -> None:
    graph = build_evidence_brief_graph(checkpointer=InMemorySaver())
    context = make_context()
    config: RunnableConfig = {"configurable": {"thread_id": "review-reject"}}
    result = graph.invoke(
        {"request": request_for("conflict-01").model_dump(), "events": [], "branch_results": []},
        config=config,
        context=context,
        version="v2",
    )
    assert result.interrupts
    result = graph.invoke(
        Command(resume={"action": "reject", "reason": "address risk"}),
        config=config,
        context=context,
        version="v2",
    )
    assert result.interrupts
    result = graph.invoke(
        Command(resume={"action": "approve", "reason": "risk addressed"}),
        config=config,
        context=context,
        version="v2",
    )
    assert result.value["status"] == "complete"
    assert result.value["revision_count"] == 1


def test_faults_have_explicit_terminal_reasons() -> None:
    missing = run_fixture("conflict-01", faults=FaultPlan(missing_task_id="exceptions"))
    assert missing["status"] == "failed"
    assert missing["terminal_reason"] == "missing branches: exceptions"
    exhausted = run_fixture(
        "conflict-01",
        review_decision={"action": "reject", "reason": "still unsafe"},
        faults=FaultPlan(revision_budget_exhausted=True),
    )
    assert exhausted["status"] == "failed"
    assert exhausted["terminal_reason"] == "revision budget exhausted"


def test_transient_failure_retries_without_duplicate_effects() -> None:
    state = run_fixture("conflict-01", faults=FaultPlan(transient_retrieval_failures=1))
    assert state["status"] == "complete"
    assert set(state["run_metrics"]["attempts"].values()) == {2}
    assert len([effect for effect in state["run_metrics"]["effects"] if effect.startswith("collect:")]) == 3
