"""Validated boundary objects for the evidence-brief workflow."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BriefRequest(StrictModel):
    question_id: str
    question: str
    audience: str = "platform steering group"
    decision_deadline: str = "before production procurement"
    source_policy: str = "fixture-only"


class SourceRecord(StrictModel):
    id: str
    title: str
    published: str
    tags: list[str]
    text: str
    available: bool = True
    in_scope: bool = True
    outdated: bool = False


class Passage(StrictModel):
    id: str
    source_id: str
    start: int
    end: int
    text: str
    query: str
    extraction_method: str = "fixture-keyword-v1"


class ResearchTask(StrictModel):
    id: str
    query: str
    source_tags: list[str]
    expected_claim_types: list[str]


class Claim(StrictModel):
    id: str
    subject: str
    predicate: str
    value: str
    text: str
    kind: Literal["evidence", "inference"]
    passage_id: str | None = None
    source_id: str | None = None
    uncertainty: str = "none"


class Contradiction(StrictModel):
    id: str
    claim_ids: list[str]
    subject: str
    resolution: str
    status: Literal["resolved", "needs_review"] = "resolved"


class ReviewRequest(StrictModel):
    artifact_version: int
    recommendation: str
    markdown: str
    unresolved_issues: list[str]
    allowed_actions: list[str] = Field(
        default_factory=lambda: ["approve", "edit", "reject", "request_evidence"]
    )


class ReviewDecision(StrictModel):
    action: Literal["approve", "edit", "reject", "request_evidence"]
    reason: str
    edited_recommendation: str | None = None


class BriefArtifact(StrictModel):
    version: int = 1
    recommendation: str
    markdown: str
    citations: list[str]
    status: Literal["draft", "verified", "exported"] = "draft"


class FaultPlan(StrictModel):
    transient_retrieval_failures: int = 0
    malformed_plan: bool = False
    missing_task_id: str | None = None
    unresolved_contradiction: bool = False
    policy_violation: bool = False
    revision_budget_exhausted: bool = False


class EvaluationRow(StrictModel):
    question_id: str
    category: str
    variant: str
    recommendation_correct: float
    evidence_coverage: float
    claim_support: float
    provenance_completeness: float
    contradiction_detection: float
    legal_transitions: float
    bounded_termination: float
    review_compliance: float
    citation_correctness: float
    resume_correctness: float
    latency_ms: int
    cost_units: int
    retries: int
    checkpoint_growth: int
    first_violated_invariant: str | None = None


class EvaluationReport(StrictModel):
    variant: str
    rows: list[EvaluationRow]
    means: dict[str, float]
