"""Validated boundary objects for the Philippine legal-research workflow."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

LegalRole = Literal["constitutional_text", "rule_text", "holding", "exception", "inference"]
Recommendation = Literal[
    "available_with_conditions",
    "requires_exception_analysis",
    "not_available_on_record",
    "insufficient_authority",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Rule65Facts(StrictModel):
    record_complete: bool
    grave_abuse_supported: bool
    adequate_appeal_available: bool
    exception_facts_supported: bool = False


class BriefRequest(StrictModel):
    question_id: str
    question: str
    facts: Rule65Facts
    jurisdiction: str = "Philippines"
    as_of: str = "2026-08-26"
    audience: str = "supervising lawyer or law professor"
    decision_deadline: str = "before relying on the memorandum"
    source_policy: str = "official Philippine sources in the pinned fixture corpus"


class SourceRecord(StrictModel):
    id: str
    title: str
    published: str
    authority_type: Literal["constitution", "rule", "decision", "secondary"]
    citation: str
    official_url: str | None = None
    tags: list[str]
    text: str
    available: bool = True
    in_scope: bool = True
    outdated: bool = False
    superseded: bool = False


class Passage(StrictModel):
    id: str
    source_id: str
    start: int
    end: int
    text: str
    query: str
    authority_type: Literal["constitution", "rule", "decision", "secondary"]
    citation: str
    official_url: str | None = None
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
    legal_role: LegalRole
    authority_citation: str | None = None
    official_url: str | None = None
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


class EvaluationCase(StrictModel):
    id: str
    category: Literal["straightforward", "qualified", "insufficient", "scope-sensitive"]
    tier: Literal["worked", "validation", "challenge"]
    pair_id: str
    question: str
    facts: Rule65Facts
    expected_recommendation: Recommendation
    required_sources: list[str]
    expects_contradiction: bool
    oracle_kind: Literal["closed_world_rule65_fixture"] = "closed_world_rule65_fixture"
    review_status: Literal["fixture_only", "expert_reviewed"] = "fixture_only"
    contamination_risk: Literal["low", "medium", "high"] = "low"


class PublicBarRecord(StrictModel):
    id: str
    year: int
    subject: str
    item_locator: str
    question_url: str
    suggested_answer_title: str
    suggested_answer_url: str
    answer_text_in_repo: bool = False
    eligible_for_scoring: bool = False
    contamination_risk: Literal["high"] = "high"
    reference_status: Literal["external_reference_required"] = "external_reference_required"
    note: str


class PublicRegressionStatus(StrictModel):
    total_records: int
    score_eligible: int
    blocked_records: int
    contamination_risk: Literal["high"] = "high"


class EvaluationRow(StrictModel):
    question_id: str
    category: str
    tier: str
    pair_id: str
    oracle_kind: str
    review_status: str
    contamination_risk: str
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
    tier_means: dict[str, dict[str, float]]
    public_bar_regression: PublicRegressionStatus
