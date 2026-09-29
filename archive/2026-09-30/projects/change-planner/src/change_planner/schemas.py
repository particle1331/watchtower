"""Typed contracts for repository snapshots, evidence, memory, and plans."""

import operator
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


SourceKind = Literal["code", "test", "config", "docs", "git", "memory"]


class ChangeRequest(StrictModel):
    scenario_id: str
    repository: str
    revision: str
    request: str
    scope: list[str] = Field(default_factory=list)
    execution_policy: Literal["read_only", "allow_targeted_tests"] = "read_only"


class RepositorySnapshot(StrictModel):
    repository: str
    revision: str
    index_id: str
    source_fingerprint: str


class FixtureSource(StrictModel):
    id: str
    repository: str
    revision: str
    source_kind: SourceKind
    path: str
    text: str
    tags: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    related_tests: list[str] = Field(default_factory=list)
    related_sources: list[str] = Field(default_factory=list)
    available: bool = True


RetrievalMethod = Literal["lexical", "dense", "hybrid", "structural", "agentic"]


class RetrievalHit(StrictModel):
    method: RetrievalMethod
    rank: int
    score: float


class RetrievalMetrics(StrictModel):
    method: RetrievalMethod
    query: str
    top_k: int
    retrieved_count: int
    relevant_count: int
    precision_at_k: float
    recall_at_k: float
    reciprocal_rank: float
    ndcg_at_k: float
    estimated_latency_ms: int
    index_cost_units: int


class Evidence(StrictModel):
    id: str
    repository: str
    revision: str
    source_kind: SourceKind
    path: str
    symbol: str | None = None
    start_line: int
    end_line: int
    content_hash: str
    text: str
    retrieval: list[RetrievalHit] = Field(default_factory=list)


class InvestigationTask(StrictModel):
    id: str
    query: str
    source_kinds: list[SourceKind]
    purpose: Literal["behavior", "tests", "operations", "history"]


class Relationship(StrictModel):
    id: str
    left_evidence_id: str
    right_evidence_id: str
    relation: Literal["defines", "tested_by", "documents", "changed_with", "configures"]
    status: Literal["candidate", "verified"] = "candidate"
    rationale: str


class RegressionHypothesis(StrictModel):
    id: str
    statement: str
    severity: Literal["low", "medium", "high"]
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    refuting_evidence_ids: list[str] = Field(default_factory=list)
    verification_steps: list[str] = Field(default_factory=list)
    status: Literal["unverified", "supported", "refuted", "unknown"] = "unverified"


class TestLink(StrictModel):
    id: str
    test_evidence_id: str
    target_evidence_ids: list[str] = Field(default_factory=list)
    relation: Literal["name_match", "symbol_match", "co_change", "coverage"]
    status: Literal["candidate", "verified"] = "candidate"


class VerificationResult(StrictModel):
    command: list[str]
    cwd: str
    status: Literal["passed", "failed", "blocked", "timed_out"]
    returncode: int | None = None
    output_fingerprint: str
    stdout: str = ""
    stderr: str = ""
    duration_ms: int
    reason: str


class MemoryRecord(StrictModel):
    id: str
    kind: Literal["episodic", "semantic", "procedural"]
    repository: str
    valid_from: str
    valid_until: str | None = None
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    investigation_id: str
    content_fingerprint: str
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["candidate", "reviewed", "invalidated"] = "candidate"


class ReviewDecision(StrictModel):
    action: Literal["approve", "edit", "reject", "request_evidence"]
    reason: str
    edited_summary: str | None = None


class ChangePlanArtifact(StrictModel):
    version: int = 1
    status: Literal["draft", "verified", "exported"] = "draft"
    summary: str
    current_behavior: list[str]
    proposed_change: list[str]
    affected_surfaces: list[str]
    regression_hypotheses: list[str]
    tests: list[str]
    rollout: list[str]
    rollback: list[str]
    observability: list[str]
    unknowns: list[str]
    evidence_ids: list[str]
    markdown: str


class FaultPlan(StrictModel):
    transient_failures: int = 0
    missing_task_id: str | None = None
    stale_index: bool = False
    malformed_plan: bool = False
    disallow_tests: bool = False
    revision_budget_exhausted: bool = False


class EvaluationCase(StrictModel):
    id: str
    category: Literal["behavior", "configuration", "regression"]
    tier: Literal["worked", "validation", "challenge"]
    question: str
    request: ChangeRequest
    expected_sources: list[str]
    expected_tests: list[str]
    expected_symbols: list[str]
    seeded_regression: bool = False


class EvaluationRow(StrictModel):
    case_id: str
    tier: str
    variant: str
    evidence_recall: float
    test_recall: float
    symbol_recall: float
    affected_file_recall: float
    affected_symbol_recall: float
    related_test_recall: float
    citation_completeness: float
    bounded_termination: float
    review_compliance: float
    resume_correctness: float
    latency_ms: int
    cost_units: int


class EvaluationReport(StrictModel):
    variant: str
    rows: list[EvaluationRow]
    means: dict[str, float]
    tier_means: dict[str, dict[str, float]]


class ChangeState(TypedDict, total=False):
    request: dict
    snapshot: dict
    tasks: list[dict]
    branch_results: Annotated[list[dict], operator.add]
    evidence: list[dict]
    relationships: list[dict]
    hypotheses: list[dict]
    test_links: list[dict]
    verification_results: list[dict]
    memory_hits: list[dict]
    memory_stored: list[dict]
    artifact: dict
    review: dict
    revision_count: int
    search_rounds: int
    verification_rounds: int
    status: str
    terminal_reason: str
    events: Annotated[list[str], operator.add]
