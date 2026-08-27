"""Cumulative LangGraph workflow for repository change investigations."""

import hashlib
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict, cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, RetryPolicy, Send, interrupt
from pydantic import ValidationError

from change_planner.adapters import ModelAdapter, ScriptedModelAdapter
from change_planner.analysis import hypotheses, relationships, test_links
from change_planner.fixtures import case_for, load_sources, request_for, snapshot
from change_planner.ingestion import IndexedRepository
from change_planner.retrieval import FixtureCatalog, hybrid_search
from change_planner.schemas import (
    ChangePlanArtifact,
    ChangeRequest,
    ChangeState,
    Evidence,
    FaultPlan,
    InvestigationTask,
    MemoryRecord,
    RegressionHypothesis,
    RepositorySnapshot,
    ReviewDecision,
    TestLink,
    VerificationResult,
)
from change_planner.verification import run_targeted_test


class TransientRetrievalError(ConnectionError):
    """Injected retryable failure for a retrieval branch."""


@dataclass
class RunController:
    attempts: dict[str, int] = field(default_factory=dict)
    effects: list[str] = field(default_factory=list)
    cost_units: int = 0
    simulated_latency_ms: int = 0

    def attempt(self, task_id: str, failures: int) -> None:
        count = self.attempts.get(task_id, 0) + 1
        self.attempts[task_id] = count
        if count <= failures:
            raise TransientRetrievalError(f"transient failure for {task_id}, attempt {count}")

    def record_effect(self, key: str) -> None:
        if key not in self.effects:
            self.effects.append(key)


@dataclass
class MemoryStore:
    records: list[MemoryRecord] = field(default_factory=list)

    def recall(
        self,
        request: ChangeRequest,
        current_snapshot: RepositorySnapshot | None = None,
    ) -> list[MemoryRecord]:
        terms = set(request.request.lower().split())
        hits: list[MemoryRecord] = []
        for record in self.records:
            if record.repository != request.repository or record.valid_until is not None:
                continue
            if current_snapshot and (
                record.valid_from != current_snapshot.revision
                or record.content_fingerprint != current_snapshot.source_fingerprint
            ):
                self.invalidate(record.id, current_snapshot.revision)
                continue
            if len(terms.intersection(record.text.lower().split())) >= 2:
                hits.append(record)
        return hits

    def invalidate(self, record_id: str, valid_until: str) -> None:
        self.records = [
            record.model_copy(update={"valid_until": valid_until, "status": "invalidated"})
            if record.id == record_id
            else record
            for record in self.records
        ]

    def delete(self, record_id: str) -> None:
        self.records = [record for record in self.records if record.id != record_id]

    def conflict_candidates(self, records: list[MemoryRecord] | None = None) -> list[tuple[str, str]]:
        """Return same-revision memory pairs that require reviewer resolution."""

        active = records if records is not None else self.records
        groups: dict[tuple[str, str, str], list[MemoryRecord]] = {}
        for record in active:
            if record.valid_until is None and record.status != "invalidated":
                key = (record.repository, record.valid_from, record.content_fingerprint)
                groups.setdefault(key, []).append(record)
        return [
            (left.id, right.id)
            for rows in groups.values()
            for index, left in enumerate(rows)
            for right in rows[index + 1 :]
        ]

    def add(self, record: MemoryRecord) -> None:
        self.records = [item for item in self.records if item.id != record.id]
        self.records.append(record)


@dataclass
class RunContext:
    model: ModelAdapter
    catalog: FixtureCatalog
    repository_snapshot: RepositorySnapshot
    repository_root: Path | None = None
    faults: FaultPlan = field(default_factory=FaultPlan)
    controller: RunController = field(default_factory=RunController)
    memory: MemoryStore = field(default_factory=MemoryStore)
    sequential: bool = False


class BranchState(TypedDict):
    task: dict[str, Any]


def _request(state: ChangeState) -> ChangeRequest:
    return ChangeRequest.model_validate(state.get("request", {}))


def _artifact(state: ChangeState) -> ChangePlanArtifact:
    return ChangePlanArtifact.model_validate(state.get("artifact", {}))


def _snapshot(state: ChangeState) -> dict[str, Any]:
    return state.get("snapshot", {})


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(row["id"]): row for row in rows}
    return [by_id[key] for key in sorted(by_id)]


def build_change_planner_graph(
    *,
    checkpointer: Any = None,
    with_review: bool = True,
    sequential: bool = False,
    with_memory: bool = True,
):
    """Build the complete graph, with small ablations for course evaluation."""

    def intake(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        request = _request(state)
        if runtime.context.faults.stale_index:
            return {
                "status": "failed",
                "terminal_reason": "index is stale for target revision",
                "events": ["intake:stale_index"],
            }
        current_snapshot = runtime.context.repository_snapshot
        hits = runtime.context.memory.recall(request, current_snapshot) if with_memory else []
        return {
            "request": request.model_dump(),
            "snapshot": current_snapshot.model_dump(),
            "memory_hits": [item.model_dump() for item in hits],
            "status": "running",
            "search_rounds": 0,
            "verification_rounds": 0,
            "revision_count": 0,
            "events": ["intake:accepted", f"memory:recalled:{len(hits)}"],
        }

    def route_intake(state: ChangeState) -> str:
        return END if state.get("status") == "failed" else "plan"

    def plan(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        request = _request(state)
        tasks = runtime.context.model.plan(request)
        if runtime.context.faults.malformed_plan:
            tasks = tasks[:2]
        return {
            "tasks": [task.model_dump() for task in tasks],
            "events": ["plan:reduced" if runtime.context.faults.malformed_plan else "plan:complete"],
        }

    def dispatch(state: ChangeState) -> list[Send]:
        return [Send("investigate_branch", {"task": task}) for task in state.get("tasks", [])]

    def investigate(task: InvestigationTask, runtime: Runtime[RunContext]) -> dict[str, Any]:
        controller = runtime.context.controller
        controller.attempt(task.id, runtime.context.faults.transient_failures)
        if task.id == runtime.context.faults.missing_task_id:
            return {
                "task_id": task.id,
                "status": "failed",
                "evidence": [],
                "observations": ["injected missing branch"],
            }
        evidence = hybrid_search(
            runtime.context.catalog,
            task.query,
            source_kinds=task.source_kinds,
            top_k=6,
        )
        controller.record_effect(f"search:{task.id}")
        controller.cost_units += 1 + len(evidence)
        latency = 10 + 5 * len(evidence)
        if runtime.context.sequential:
            controller.simulated_latency_ms += latency
        else:
            controller.simulated_latency_ms = max(controller.simulated_latency_ms, latency)
        return {
            "task_id": task.id,
            "status": "complete" if evidence else "incomplete",
            "evidence": [item.model_dump() for item in evidence],
            "observations": [f"{len(evidence)} evidence records"],
        }

    def investigate_branch(state: BranchState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        task = InvestigationTask.model_validate(state["task"])
        return {
            "branch_results": [investigate(task, runtime)],
            "events": [f"investigate:{task.id}"],
        }

    def investigate_sequential(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        results = [
            investigate(InvestigationTask.model_validate(task), runtime)
            for task in state.get("tasks", [])
        ]
        return {"branch_results": results, "events": ["investigate:sequential"]}

    def join(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        latest = {result["task_id"]: result for result in state.get("branch_results", [])}
        expected = {task["id"] for task in state.get("tasks", [])}
        missing = sorted(task_id for task_id in expected if task_id not in latest)
        failed = sorted(task_id for task_id, result in latest.items() if result.get("status") == "failed")
        evidence = _dedupe(
            [item for result in latest.values() for item in result.get("evidence", [])]
        )
        if missing or failed:
            reason = ", ".join(missing + failed)
            return {
                "evidence": evidence,
                "status": "failed",
                "terminal_reason": f"incomplete investigation branches: {reason}",
                "events": ["join:gap"],
            }
        parsed = [Evidence.model_validate(item) for item in evidence]
        rels = relationships(runtime.context.catalog, parsed)
        links = test_links(runtime.context.catalog, parsed)
        return {
            "evidence": evidence,
            "relationships": [item.model_dump() for item in rels],
            "test_links": [item.model_dump() for item in links],
            "events": ["join:complete"],
        }

    def route_join(state: ChangeState) -> str:
        return END if state.get("status") == "failed" else "analyze"

    def analyze(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        request = _request(state)
        evidence = [Evidence.model_validate(item) for item in state.get("evidence", [])]
        risks = hypotheses(request, runtime.context.catalog, evidence)
        return {"hypotheses": [item.model_dump() for item in risks], "events": ["analyze:complete"]}

    def route_analysis(state: ChangeState) -> str:
        request = _request(state)
        if not state.get("evidence"):
            if state.get("search_rounds", 0) < 1:
                return "refine"
            return END
        if request.execution_policy == "allow_targeted_tests" and state.get("test_links"):
            return "verify_tests"
        return "draft"

    def refine(state: ChangeState) -> dict[str, Any]:
        return {
            "search_rounds": state.get("search_rounds", 0) + 1,
            "events": ["refine:requested"],
        }

    def verify_tests(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        if runtime.context.faults.disallow_tests:
            return {
                "status": "failed",
                "terminal_reason": "targeted test execution disallowed by policy",
                "events": ["tests:blocked"],
            }
        links = [TestLink.model_validate(item) for item in state.get("test_links", [])]
        request = _request(state)
        if runtime.context.repository_root:
            evidence_by_id = {item["id"]: item for item in state.get("evidence", [])}
            verification = []
            verified = []
            for link in links:
                test_path = evidence_by_id[link.test_evidence_id]["path"]
                result = run_targeted_test(
                    runtime.context.repository_root,
                    [sys.executable, "-m", "pytest", test_path],
                    authorized=True,
                )
                verification.append(result)
                if result.status == "passed":
                    verified.append(link.model_copy(update={"status": "verified"}))
                else:
                    verified.append(link)
        else:
            verified = [item.model_copy(update={"status": "verified"}) for item in links]
            verification = [
                VerificationResult(
                    command=["fixture-test", link.id],
                    cwd=request.repository,
                    status="passed",
                    returncode=0,
                    output_fingerprint=f"sha256:{hashlib.sha256(link.id.encode()).hexdigest()}",
                    duration_ms=0,
                    reason="fixture verification observed a passing targeted test",
                )
                for link in verified
            ]
        for link in verified:
            if link.status == "verified":
                runtime.context.controller.record_effect(f"test:{link.id}")
        failed = [item for item in verification if item.status != "passed"]
        return {
            "test_links": [item.model_dump() for item in verified],
            "verification_results": [item.model_dump() for item in verification],
            "verification_rounds": state.get("verification_rounds", 0) + 1,
            "status": "failed" if failed else "running",
            "terminal_reason": "targeted verification failed" if failed else "",
            "events": ["tests:failed" if failed else "tests:verified"],
        }

    def route_after_tests(state: ChangeState) -> str:
        return END if state.get("status") == "failed" else "draft"

    def draft(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        request = _request(state)
        evidence = [Evidence.model_validate(item) for item in state.get("evidence", [])]
        links = [TestLink.model_validate(item) for item in state.get("test_links", [])]
        risks = [RegressionHypothesis.model_validate(item) for item in state.get("hypotheses", [])]
        artifact = runtime.context.model.draft(request, evidence, links, risks)
        return {"artifact": artifact.model_dump(), "events": ["draft:created"]}

    def review(state: ChangeState) -> Command:
        artifact = _artifact(state)
        raw = interrupt(
            {
                "artifact_version": artifact.version,
                "summary": artifact.summary,
                "unknowns": artifact.unknowns,
                "allowed_actions": ["approve", "edit", "reject", "request_evidence"],
            }
        )
        try:
            decision = ReviewDecision.model_validate(raw)
        except ValidationError as exc:
            return Command(update={"events": [f"review:malformed:{exc.__class__.__name__}"]}, goto="review")
        if decision.action == "approve":
            return Command(update={"review": decision.model_dump(), "events": ["review:approved"]}, goto="verify")
        if decision.action == "edit":
            edited = artifact.model_copy(
                update={
                    "version": artifact.version + 1,
                    "summary": decision.edited_summary or artifact.summary,
                    "markdown": artifact.markdown + f"\n\nReviewer note: {decision.reason}",
                }
            )
            return Command(
                update={"artifact": edited.model_dump(), "review": decision.model_dump(), "events": ["review:edited"]},
                goto="verify",
            )
        if decision.action == "request_evidence":
            return Command(update={"review": decision.model_dump(), "events": ["review:requested_evidence"]}, goto="refine")
        return Command(update={"review": decision.model_dump(), "events": ["review:rejected"]}, goto="revise")

    def auto_review(state: ChangeState) -> Command:
        return Command(
            update={"review": ReviewDecision(action="approve", reason="evaluation auto-review").model_dump(), "events": ["review:auto_approved"]},
            goto="verify",
        )

    def revise(state: ChangeState, runtime: Runtime[RunContext]) -> Command:
        count = state.get("revision_count", 0) + 1
        if runtime.context.faults.revision_budget_exhausted or count > 1:
            return Command(update={"status": "failed", "terminal_reason": "revision budget exhausted", "events": ["revise:exhausted"]}, goto=END)
        artifact = _artifact(state)
        revised = artifact.model_copy(
            update={"version": artifact.version + 1, "markdown": artifact.markdown + "\n\nRevision incorporated."}
        )
        return Command(update={"artifact": revised.model_dump(), "revision_count": count, "events": ["revise:complete"]}, goto="review")

    def verify(state: ChangeState) -> Command:
        artifact = _artifact(state)
        evidence_ids = {item["id"] for item in state.get("evidence", [])}
        if any(item not in evidence_ids for item in artifact.evidence_ids):
            return Command(update={"status": "failed", "terminal_reason": "plan cites missing evidence", "events": ["verify:failed"]}, goto=END)
        return Command(
            update={"artifact": artifact.model_copy(update={"status": "verified"}).model_dump(), "events": ["verify:passed"]},
            goto="remember" if with_memory else "export",
        )

    def remember(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        request = _request(state)
        record = MemoryRecord(
            id=f"{request.repository}:{request.scenario_id}",
            kind="episodic",
            repository=request.repository,
            valid_from=request.revision,
            text=f"{request.request}\n{_artifact(state).summary}",
            evidence_ids=[item["id"] for item in state.get("evidence", [])],
            investigation_id=request.scenario_id,
            content_fingerprint=_snapshot(state).get("source_fingerprint", ""),
            confidence=0.9,
            status="reviewed",
        )
        runtime.context.memory.add(record)
        return {"events": ["memory:stored"], "memory_stored": [record.model_dump()]}

    def export(state: ChangeState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        artifact = _artifact(state)
        runtime.context.controller.record_effect("export:plan")
        return {
            "artifact": artifact.model_copy(update={"status": "exported"}).model_dump(),
            "status": "complete",
            "terminal_reason": "completion contract satisfied",
            "events": ["export:complete"],
        }

    builder = StateGraph(ChangeState, context_schema=RunContext)
    builder.add_node("intake", intake)
    builder.add_node("plan", plan)
    builder.add_node(
        "investigate_branch",
        investigate_branch,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_interval=0.0,
            backoff_factor=1.0,
            max_interval=0.0,
            jitter=False,
            retry_on=TransientRetrievalError,
        ),
    )
    builder.add_node("investigate_sequential", investigate_sequential)
    builder.add_node("join", join)
    builder.add_node("analyze", analyze)
    builder.add_node("refine", refine)
    builder.add_node("verify_tests", verify_tests)
    builder.add_node("draft", draft)
    builder.add_node("review", review if with_review else auto_review, destinations=("verify", "revise", "refine", "review"))
    builder.add_node("revise", revise, destinations=("review", END))
    builder.add_node("verify", verify, destinations=("remember", "export", END))
    builder.add_node("remember", remember)
    builder.add_node("export", export)
    builder.add_edge(START, "intake")
    builder.add_conditional_edges("intake", route_intake, ["plan", END])
    if sequential:
        builder.add_edge("plan", "investigate_sequential")
        builder.add_edge("investigate_sequential", "join")
    else:
        builder.add_conditional_edges("plan", dispatch, ["investigate_branch"])
        builder.add_edge("investigate_branch", "join")
    builder.add_conditional_edges("join", route_join, ["analyze", END])
    builder.add_conditional_edges("analyze", route_analysis, ["refine", "verify_tests", "draft", END])
    builder.add_edge("refine", "plan")
    builder.add_conditional_edges("verify_tests", route_after_tests, ["draft", END])
    builder.add_edge("draft", "review")
    builder.add_edge("remember", "export")
    builder.add_edge("export", END)
    saver = checkpointer if checkpointer is not None else (InMemorySaver() if with_review else False)
    return builder.compile(checkpointer=saver)


def make_context(
    faults: FaultPlan | None = None,
    *,
    catalog: FixtureCatalog | None = None,
    repository_snapshot: RepositorySnapshot | None = None,
    repository_root: Path | None = None,
    memory: MemoryStore | None = None,
    sequential: bool = False,
) -> RunContext:
    return RunContext(
        model=ScriptedModelAdapter(),
        catalog=catalog or FixtureCatalog(load_sources()),
        repository_snapshot=repository_snapshot or snapshot(),
        repository_root=repository_root,
        faults=faults or FaultPlan(),
        memory=memory or MemoryStore(),
        sequential=sequential,
    )


def _run_request(
    request: ChangeRequest,
    context: RunContext,
    *,
    review_decision: ReviewDecision | dict[str, Any] | None = None,
    variant: str = "full",
) -> dict[str, Any]:
    with_review = variant not in {"no_review", "no_checkpointing"}
    graph = build_change_planner_graph(
        with_review=with_review,
        sequential=context.sequential,
        with_memory=variant != "no_memory",
        checkpointer=False if variant == "no_checkpointing" else None,
    )
    config: RunnableConfig = {"configurable": {"thread_id": f"request-{request.scenario_id}-{variant}"}}
    result = graph.invoke(
        {"request": request.model_dump(), "events": [], "branch_results": []},
        config=config,
        context=context,
        version="v2",
    )
    if result.interrupts:
        decision = review_decision or ReviewDecision(action="approve", reason="automatic approval")
        payload = decision.model_dump() if isinstance(decision, ReviewDecision) else decision
        result = graph.invoke(Command(resume=payload), config=config, context=context, version="v2")
    state = dict(result.value)
    state["run_metrics"] = {
        "attempts": dict(context.controller.attempts),
        "effects": list(context.controller.effects),
        "cost_units": context.controller.cost_units,
        "simulated_latency_ms": context.controller.simulated_latency_ms,
    }
    return state


def run_fixture(
    scenario_id: str = "dry-run-01",
    *,
    review_decision: ReviewDecision | dict[str, Any] | None = None,
    faults: FaultPlan | None = None,
    variant: str = "full",
    memory: MemoryStore | None = None,
) -> dict[str, Any]:
    context = make_context(faults, memory=memory, sequential=variant == "sequential")
    state = _run_request(
        request_for(scenario_id),
        context,
        review_decision=review_decision,
        variant=variant,
    )
    state["scenario"] = case_for(scenario_id).model_dump()
    return state


def run_indexed(
    indexed: IndexedRepository,
    request: ChangeRequest,
    *,
    review_decision: ReviewDecision | dict[str, Any] | None = None,
    faults: FaultPlan | None = None,
    variant: str = "full",
    memory: MemoryStore | None = None,
) -> dict[str, Any]:
    """Run the planner against an ingested repository snapshot."""

    if request.repository != indexed.snapshot.repository or request.revision != indexed.snapshot.revision:
        raise ValueError("change request identity does not match the indexed repository snapshot")
    context = make_context(
        faults,
        catalog=indexed.catalog,
        repository_snapshot=indexed.snapshot,
        repository_root=indexed.root,
        memory=memory,
        sequential=variant == "sequential",
    )
    return _run_request(request, context, review_decision=review_decision, variant=variant)


def stream_fixture(
    scenario_id: str = "dry-run-01",
    *,
    variant: str = "no_review",
) -> Iterator[dict[str, Any]]:
    """Yield public node/event updates without exposing model-private content."""

    context = make_context(sequential=variant == "sequential")
    graph = build_change_planner_graph(
        with_review=False,
        sequential=variant == "sequential",
        with_memory=variant != "no_memory",
    )
    config: RunnableConfig = {"configurable": {"thread_id": f"stream-{scenario_id}-{variant}"}}
    initial: ChangeState = {
        "request": request_for(scenario_id).model_dump(),
        "events": [],
        "branch_results": [],
    }
    for envelope in graph.stream(
        initial,
        config=config,
        context=context,
        stream_mode="updates",
        version="v2",
    ):
        if not isinstance(envelope, dict):
            continue
        updates = cast(dict[str, Any], envelope.get("data", {}))
        for node, update in updates.items():
            update_dict = cast(dict[str, Any], update)
            yield {"node": node, "events": update_dict.get("events", [])}
