"""Deterministic planning and drafting adapters."""

from typing import Protocol

from change_planner.analysis import render_plan
from change_planner.schemas import (
    ChangePlanArtifact,
    ChangeRequest,
    Evidence,
    InvestigationTask,
    RegressionHypothesis,
    TestLink,
)


class ModelAdapter(Protocol):
    def plan(self, request: ChangeRequest) -> list[InvestigationTask]: ...

    def draft(
        self,
        request: ChangeRequest,
        evidence: list[Evidence],
        links: list[TestLink],
        hypotheses: list[RegressionHypothesis],
    ) -> ChangePlanArtifact: ...


class ScriptedModelAdapter:
    """Keeps the course artifact stable while graph semantics are being tested."""

    def plan(self, request: ChangeRequest) -> list[InvestigationTask]:
        retry = "retry" in request.request.lower()
        common = [
            InvestigationTask(
                id="behavior",
                query=request.request,
                source_kinds=["code", "config"],
                purpose="behavior",
            ),
            InvestigationTask(
                id="tests",
                query=f"tests coverage behavior {request.request}",
                source_kinds=["test"],
                purpose="tests",
            ),
            InvestigationTask(
                id="operations",
                query=f"documentation configuration rollout rollback {request.request}",
                source_kinds=["docs", "config"],
                purpose="operations",
            ),
            InvestigationTask(
                id="history",
                query=f"prior change regression history {request.request}",
                source_kinds=["git"],
                purpose="history",
            ),
        ]
        if retry:
            return common
        return common

    def draft(
        self,
        request: ChangeRequest,
        evidence: list[Evidence],
        links: list[TestLink],
        hypotheses: list[RegressionHypothesis],
    ) -> ChangePlanArtifact:
        return render_plan(request, evidence, links, hypotheses)
