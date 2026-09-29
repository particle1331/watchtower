"""Cumulative LangGraph workflow for a deterministic legal research memorandum."""

# pyright: reportTypedDictNotRequiredAccess=false

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, RetryPolicy, Send, interrupt
from pydantic import ValidationError

from evidence_brief.adapters import ModelAdapter, ScriptedModelAdapter
from evidence_brief.domain import FixtureCatalog, retrieve, verify_claim
from evidence_brief.fixtures import load_corpus, question_record, request_for
from evidence_brief.schemas import (
    BriefArtifact,
    BriefRequest,
    Claim,
    Contradiction,
    FaultPlan,
    Passage,
    ResearchTask,
    ReviewDecision,
    ReviewRequest,
)


class TransientRetrievalError(ConnectionError):
    """Injected retryable retrieval failure."""


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
class RunContext:
    model: ModelAdapter
    catalog: FixtureCatalog
    faults: FaultPlan = field(default_factory=FaultPlan)
    controller: RunController = field(default_factory=RunController)


class BriefState(TypedDict, total=False):
    request: dict[str, Any]
    tasks: list[dict[str, Any]]
    branch_results: Annotated[list[dict[str, Any]], operator.add]
    passages: list[dict[str, Any]]
    claims: list[dict[str, Any]]
    contradictions: list[dict[str, Any]]
    artifact: dict[str, Any]
    review: dict[str, Any]
    review_error: str
    revision_count: int
    research_attempts: int
    status: str
    terminal_reason: str
    events: Annotated[list[str], operator.add]


class BranchState(TypedDict):
    task: dict[str, Any]


def _dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id = {str(row["id"]): row for row in rows}
    return [by_id[key] for key in sorted(by_id)]


def build_evidence_brief_graph(
    *,
    checkpointer: Any = None,
    store: Any = None,
    with_review: bool = True,
    sequential: bool = False,
    reconcile_evidence: bool = True,
):
    """Build the complete graph with configurable evaluation ablations."""

    def intake(state: BriefState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        request = BriefRequest.model_validate(state["request"])
        if runtime.context.faults.policy_violation:
            return {
                "status": "failed",
                "terminal_reason": "source policy violation",
                "events": ["intake:policy_rejected"],
            }
        return {"request": request.model_dump(), "status": "running", "events": ["intake:accepted"]}

    def route_intake(state: BriefState) -> str:
        return END if state.get("status") == "failed" else "plan"

    def plan(state: BriefState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        request = BriefRequest.model_validate(state["request"])
        tasks = runtime.context.model.plan(request)
        event = "plan:repaired" if runtime.context.faults.malformed_plan else "plan:valid"
        return {"tasks": [task.model_dump() for task in tasks], "events": [event]}

    def dispatch(state: BriefState) -> list[Send]:
        return [Send("collect_branch", {"task": task}) for task in state["tasks"]]

    def run_branch(task: ResearchTask, runtime: Runtime[RunContext]) -> dict[str, Any]:
        controller = runtime.context.controller
        controller.attempt(task.id, runtime.context.faults.transient_retrieval_failures)
        if task.id == runtime.context.faults.missing_task_id:
            return {"task_id": task.id, "status": "failed", "passages": [], "claims": [], "observations": ["injected missing branch"]}
        passages, observations = retrieve(runtime.context.catalog, task)
        claims: list[Claim] = []
        for passage in passages:
            claims.extend(runtime.context.model.extract(passage))
        controller.record_effect(f"collect:{task.id}")
        controller.cost_units += 1 + len(passages)
        latency = {"controlling_text": 20, "general_rule": 30, "exceptions": 40}[task.id]
        controller.simulated_latency_ms += latency if sequential else max(0, latency - controller.simulated_latency_ms)
        return {
            "task_id": task.id,
            "status": "complete",
            "passages": [item.model_dump() for item in passages],
            "claims": [item.model_dump() for item in claims],
            "observations": [item.__dict__ for item in observations],
        }

    def collect_branch(state: BranchState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        task = ResearchTask.model_validate(state["task"])
        return {"branch_results": [run_branch(task, runtime)], "events": [f"collect:{task.id}"]}

    def collect_sequential(state: BriefState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        results = [run_branch(ResearchTask.model_validate(task), runtime) for task in state["tasks"]]
        return {"branch_results": results, "events": ["collect:sequential"]}

    def join(state: BriefState) -> dict[str, Any]:
        latest = {result["task_id"]: result for result in state.get("branch_results", [])}
        expected = {task["id"] for task in state["tasks"]}
        failed = sorted(task_id for task_id in expected if task_id not in latest or latest[task_id]["status"] != "complete")
        passages = _dedupe([item for result in latest.values() for item in result["passages"]])
        claims = _dedupe([item for result in latest.values() for item in result["claims"]])
        if failed:
            return {
                "passages": passages,
                "claims": claims,
                "status": "failed",
                "terminal_reason": f"missing branches: {', '.join(failed)}",
                "events": ["join:gap"],
            }
        return {"passages": passages, "claims": claims, "events": ["join:complete"]}

    def route_join(state: BriefState) -> str:
        if state.get("status") == "failed":
            return END
        return "reconcile" if reconcile_evidence else "draft"

    def reconcile(state: BriefState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        claims = [Claim.model_validate(item) for item in state["claims"]]
        contradictions = runtime.context.model.reconcile(claims)
        if runtime.context.faults.unresolved_contradiction:
            contradictions = [item.model_copy(update={"status": "needs_review"}) for item in contradictions]
        return {
            "contradictions": [item.model_dump() for item in contradictions],
            "events": ["reconcile:complete"],
        }

    def draft(state: BriefState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        request = BriefRequest.model_validate(state["request"])
        claims = [Claim.model_validate(item) for item in state["claims"]]
        contradictions = [Contradiction.model_validate(item) for item in state.get("contradictions", [])]
        artifact = runtime.context.model.draft(request, claims, contradictions)
        return {"artifact": artifact.model_dump(), "events": ["draft:created"]}

    def review(state: BriefState) -> Command:
        artifact = BriefArtifact.model_validate(state["artifact"])
        contradictions = [Contradiction.model_validate(item) for item in state.get("contradictions", [])]
        request = ReviewRequest(
            artifact_version=artifact.version,
            recommendation=artifact.recommendation,
            markdown=artifact.markdown,
            unresolved_issues=[item.subject for item in contradictions if item.status == "needs_review"],
        )
        raw = interrupt(request.model_dump())
        try:
            decision = ReviewDecision.model_validate(raw)
        except ValidationError as exc:
            return Command(
                update={"review_error": str(exc), "events": ["review:malformed"]},
                goto="review",
            )
        if decision.action == "approve":
            return Command(
                update={"review": decision.model_dump(), "events": ["review:approved"]},
                goto="verify",
            )
        if decision.action == "edit":
            recommendation = decision.edited_recommendation or artifact.recommendation
            edited = artifact.model_copy(
                update={
                    "recommendation": recommendation,
                    "version": artifact.version + 1,
                    "markdown": artifact.markdown.replace(
                        f"**{artifact.recommendation.replace('_', ' ').capitalize()}**",
                        f"**{recommendation.replace('_', ' ').capitalize()}**",
                        1,
                    ),
                }
            )
            return Command(
                update={"artifact": edited.model_dump(), "review": decision.model_dump(), "events": ["review:edited"]},
                goto="verify",
            )
        if decision.action == "request_evidence":
            return Command(
                update={"review": decision.model_dump(), "events": ["review:requested_evidence"]},
                goto="plan",
            )
        return Command(
            update={"review": decision.model_dump(), "events": ["review:rejected"]},
            goto="revise",
        )

    def auto_review(state: BriefState) -> Command:
        decision = ReviewDecision(action="approve", reason="evaluation auto-review")
        return Command(
            update={"review": decision.model_dump(), "events": ["review:auto_approved"]},
            goto="verify",
        )

    def revise(state: BriefState, runtime: Runtime[RunContext]) -> Command:
        count = state.get("revision_count", 0) + 1
        if runtime.context.faults.revision_budget_exhausted or count > 1:
            return Command(
                update={
                    "revision_count": count,
                    "status": "failed",
                    "terminal_reason": "revision budget exhausted",
                    "events": ["revise:exhausted"],
                },
                goto=END,
            )
        artifact = BriefArtifact.model_validate(state["artifact"])
        revised = artifact.model_copy(
            update={"version": artifact.version + 1, "markdown": artifact.markdown + "\n\nReviewer concerns were incorporated."}
        )
        return Command(
            update={"artifact": revised.model_dump(), "revision_count": count, "events": ["revise:complete"]},
            goto="review",
        )

    def verify(state: BriefState) -> Command:
        passages = [Passage.model_validate(item) for item in state["passages"]]
        claims = [Claim.model_validate(item) for item in state["claims"]]
        invalid = [claim.id for claim in claims if not verify_claim(claim, passages)]
        artifact = BriefArtifact.model_validate(state["artifact"])
        if invalid:
            return Command(
                update={
                    "status": "failed",
                    "terminal_reason": f"unsupported claims: {', '.join(invalid)}",
                    "events": ["verify:failed"],
                },
                goto=END,
            )
        return Command(
            update={"artifact": artifact.model_copy(update={"status": "verified"}).model_dump(), "events": ["verify:passed"]},
            goto="export",
        )

    def export(state: BriefState, runtime: Runtime[RunContext]) -> dict[str, Any]:
        artifact = BriefArtifact.model_validate(state["artifact"])
        runtime.context.controller.record_effect("export:artifact")
        return {
            "artifact": artifact.model_copy(update={"status": "exported"}).model_dump(),
            "status": "complete",
            "terminal_reason": "completion contract satisfied",
            "events": ["export:complete"],
        }

    builder = StateGraph(BriefState, context_schema=RunContext)
    builder.add_node("intake", intake)
    builder.add_node("plan", plan)
    builder.add_node(
        "collect_branch",
        collect_branch,
        retry_policy=RetryPolicy(
            max_attempts=3,
            initial_interval=0.0,
            backoff_factor=1.0,
            max_interval=0.0,
            jitter=False,
            retry_on=TransientRetrievalError,
        ),
    )
    builder.add_node("collect_sequential", collect_sequential)
    builder.add_node("join", join)
    builder.add_node("reconcile", reconcile)
    builder.add_node("draft", draft)
    builder.add_node("review", review if with_review else auto_review, destinations=("verify", "revise", "plan", "review"))
    builder.add_node("revise", revise, destinations=("review", END))
    builder.add_node("verify", verify, destinations=("export", END))
    builder.add_node("export", export)
    builder.add_edge(START, "intake")
    builder.add_conditional_edges("intake", route_intake, ["plan", END])
    if sequential:
        builder.add_edge("plan", "collect_sequential")
        builder.add_edge("collect_sequential", "join")
    else:
        builder.add_conditional_edges("plan", dispatch, ["collect_branch"])
        builder.add_edge("collect_branch", "join")
    builder.add_conditional_edges("join", route_join, ["reconcile", "draft", END])
    builder.add_edge("reconcile", "draft")
    builder.add_edge("draft", "review")
    builder.add_edge("export", END)
    saver = checkpointer if checkpointer is not None else (InMemorySaver() if with_review else False)
    return builder.compile(checkpointer=saver, store=store)


def make_context(faults: FaultPlan | None = None) -> RunContext:
    return RunContext(
        model=ScriptedModelAdapter(),
        catalog=FixtureCatalog(load_corpus()),
        faults=faults or FaultPlan(),
    )


def run_fixture(
    question_id: str = "conflict-01",
    *,
    review_decision: ReviewDecision | dict[str, Any] | None = None,
    faults: FaultPlan | None = None,
    variant: Literal["full", "sequential", "no_review", "no_reconciliation", "no_checkpointing"] = "full",
) -> dict[str, Any]:
    context = make_context(faults)
    with_review = variant not in {"no_review", "no_checkpointing"}
    graph = build_evidence_brief_graph(
        with_review=with_review,
        sequential=variant == "sequential",
        reconcile_evidence=variant != "no_reconciliation",
    )
    config: RunnableConfig = {
        "configurable": {"thread_id": f"fixture-{question_id}-{variant}"}
    }
    result = graph.invoke(
        {"request": request_for(question_id).model_dump(), "events": [], "branch_results": []},
        config=config,
        context=context,
        version="v2",
    )
    if result.interrupts:
        decision = review_decision or ReviewDecision(action="approve", reason="fixture approval")
        payload = decision.model_dump() if isinstance(decision, ReviewDecision) else decision
        result = graph.invoke(Command(resume=payload), config=config, context=context, version="v2")
    state = dict(result.value)
    state["run_metrics"] = {
        "attempts": dict(context.controller.attempts),
        "effects": list(context.controller.effects),
        "cost_units": context.controller.cost_units,
        "simulated_latency_ms": context.controller.simulated_latency_ms,
    }
    state["oracle"] = question_record(question_id).model_dump()
    return state
