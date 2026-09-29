from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from change_planner.fixtures import request_for, snapshot
from change_planner.ingestion import ingest_repository
from change_planner.schemas import ChangeState, FaultPlan, MemoryRecord, ReviewDecision
from change_planner.workflow import (
    MemoryStore,
    build_change_planner_graph,
    make_context,
    run_fixture,
    run_indexed,
    stream_fixture,
)


def test_happy_path_exports_a_cited_change_plan() -> None:
    state = run_fixture("dry-run-01")

    assert state["status"] == "complete"
    assert state["artifact"]["status"] == "exported"
    assert state["artifact"]["evidence_ids"]
    assert state["verification_results"][0]["status"] == "passed"
    assert "dry-run" in state["artifact"]["summary"]
    assert state["run_metrics"]["effects"][-1] == "export:plan"


def test_retry_scenario_surfaces_duplicate_write_risk() -> None:
    state = run_fixture("retry-01")

    assert state["status"] == "complete"
    assert state["hypotheses"][0]["id"] == "duplicate-write-on-timeout"
    assert any("no_duplicate_write" in step for step in state["hypotheses"][0]["verification_steps"])


def test_transient_branch_failure_retries_without_duplicate_search_effect() -> None:
    state = run_fixture("dry-run-01", faults=FaultPlan(transient_failures=1))

    assert state["status"] == "complete"
    assert all(value == 2 for value in state["run_metrics"]["attempts"].values())
    assert len([effect for effect in state["run_metrics"]["effects"] if effect.startswith("search:")]) == 4


def test_stale_index_and_missing_branch_terminate_explicitly() -> None:
    stale = run_fixture("dry-run-01", faults=FaultPlan(stale_index=True))
    missing = run_fixture("dry-run-01", faults=FaultPlan(missing_task_id="tests"))

    assert stale["status"] == "failed"
    assert stale["terminal_reason"] == "index is stale for target revision"
    assert missing["status"] == "failed"
    assert "tests" in missing["terminal_reason"]


def test_review_edit_changes_the_versioned_plan() -> None:
    state = run_fixture(
        "dry-run-01",
        review_decision=ReviewDecision(
            action="edit",
            reason="make the scope explicit",
            edited_summary="Review the dry-run boundary before implementation.",
        ),
    )

    assert state["status"] == "complete"
    assert state["artifact"]["version"] == 2
    assert state["artifact"]["summary"].startswith("Review the dry-run")


def test_memory_can_be_shared_across_investigations() -> None:
    memory = MemoryStore()
    first = run_fixture("dry-run-01", memory=memory)
    second = run_fixture("dry-run-01", memory=memory)

    assert first["status"] == second["status"] == "complete"
    assert any(item["investigation_id"] == "dry-run-01" for item in second["memory_hits"])


def test_memory_invalidates_records_from_another_revision_or_fingerprint() -> None:
    memory = MemoryStore()
    memory.add(
        MemoryRecord(
            id="stale",
            kind="episodic",
            repository="fixture/change-cli",
            valid_from="old-revision",
            text="dry-run clear outputs",
            investigation_id="old-run",
            content_fingerprint="sha256:old",
            confidence=0.8,
            status="reviewed",
        )
    )

    assert memory.recall(request_for("dry-run-01"), snapshot()) == []
    assert memory.records[0].status == "invalidated"
    assert memory.records[0].valid_until == "8f2c1d"


def test_indexed_repository_runs_against_its_snapshot(tmp_path) -> None:
    (tmp_path / "service.py").write_text(
        "def deploy():\n    return True\n", encoding="utf-8"
    )
    indexed = ingest_repository(tmp_path, repository="fixture/service", revision="abc123")
    request = request_for("dry-run-01").model_copy(
        update={
            "scenario_id": "local",
            "repository": indexed.snapshot.repository,
            "revision": indexed.snapshot.revision,
            "request": "deploy service",
        }
    )

    state = run_indexed(indexed, request, variant="no_review")

    assert state["snapshot"] == indexed.snapshot.model_dump()
    assert state["status"] in {"complete", "failed"}
    assert all(item["repository"] == "fixture/service" for item in state.get("evidence", []))


def test_indexed_repository_runs_only_authorized_targeted_tests(tmp_path) -> None:
    (tmp_path / "service.py").write_text(
        "def deploy():\n    return True\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_service.py").write_text(
        "from service import deploy\n\n\ndef test_deploy():\n    assert deploy()\n",
        encoding="utf-8",
    )
    indexed = ingest_repository(tmp_path, repository="fixture/service", revision="abc123")
    request = request_for("dry-run-01").model_copy(
        update={
            "scenario_id": "local-tests",
            "repository": indexed.snapshot.repository,
            "revision": indexed.snapshot.revision,
            "request": "deploy service",
            "execution_policy": "allow_targeted_tests",
        }
    )

    state = run_indexed(indexed, request, variant="no_review")

    assert state["status"] == "complete"
    assert state["verification_results"]
    assert state["verification_results"][0]["status"] == "passed"
    assert state["verification_results"][0]["command"][1:3] == ["-m", "pytest"]


def test_graph_variant_without_review_is_explicitly_measurable() -> None:
    state = run_fixture("dry-run-01", variant="no_review")

    assert state["status"] == "complete"
    assert state["review"]["action"] == "approve"


def test_graph_can_be_built_for_direct_notebook_inspection() -> None:
    graph = build_change_planner_graph(with_review=False)
    assert "join" in graph.nodes


def test_sqlite_restart_resumes_without_duplicate_effects(tmp_path) -> None:
    database = tmp_path / "restart.sqlite"
    config: RunnableConfig = {"configurable": {"thread_id": "restart-test"}}
    context = make_context()
    initial: ChangeState = {
        "request": request_for("dry-run-01").model_dump(),
        "events": [],
        "branch_results": [],
    }

    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = build_change_planner_graph(checkpointer=saver)
        paused = graph.invoke(initial, config=config, context=context, version="v2")
        assert paused.interrupts

    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = build_change_planner_graph(checkpointer=saver)
        completed = graph.invoke(
            Command(resume={"action": "approve", "reason": "restart test"}),
            config=config,
            context=context,
            version="v2",
        )

    assert completed.value.get("status") == "complete"
    assert context.controller.effects.count("search:behavior") == 1
    assert context.controller.effects.count("export:plan") == 1


def test_stream_exposes_public_node_events_without_model_content() -> None:
    events = list(stream_fixture("dry-run-01"))

    assert events
    assert {"intake", "plan", "join", "draft", "export"}.issubset(
        {event["node"] for event in events}
    )
    assert all(set(event) == {"node", "events"} for event in events)
