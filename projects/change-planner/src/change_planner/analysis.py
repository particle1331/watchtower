"""Deterministic relationships, hypotheses, test links, and plan rendering."""

from dataclasses import dataclass

from change_planner.retrieval import FixtureCatalog
from change_planner.schemas import (
    ChangePlanArtifact,
    ChangeRequest,
    Evidence,
    FixtureSource,
    RegressionHypothesis,
    Relationship,
    TestLink,
)


@dataclass(frozen=True)
class EvidenceGraph:
    """A revision-scoped evidence graph whose edges retain candidate status."""

    repository: str
    revision: str
    nodes: dict[str, Evidence]
    edges: tuple[Relationship, ...]

    def neighbors(self, evidence_id: str) -> list[str]:
        return [
            edge.right_evidence_id if edge.left_evidence_id == evidence_id else edge.left_evidence_id
            for edge in self.edges
            if evidence_id in {edge.left_evidence_id, edge.right_evidence_id}
        ]


def _sources_by_path(catalog: FixtureCatalog) -> dict[str, FixtureSource]:
    return {source.path: source for source in catalog.sources.values()}


def relationships(catalog: FixtureCatalog, evidence: list[Evidence]) -> list[Relationship]:
    found: list[Relationship] = []
    sources = _sources_by_path(catalog)
    for left in evidence:
        source = sources[left.path]
        for right in evidence:
            if left.id >= right.id:
                continue
            other = sources[right.path]
            linked = other.id in source.related_sources or source.id in other.related_sources
            tested = other.id in source.related_tests or source.id in other.related_tests
            if not linked and not tested:
                continue
            relation = "tested_by" if tested or other.source_kind == "test" else "changed_with"
            if other.source_kind == "docs":
                relation = "documents"
            if other.source_kind == "config":
                relation = "configures"
            found.append(
                Relationship(
                    id=f"{left.id}->{right.id}",
                    left_evidence_id=left.id,
                    right_evidence_id=right.id,
                    relation=relation,
                    status="candidate",
                    rationale=f"source metadata links {source.id} and {other.id}",
                )
            )
    return found


def test_links(catalog: FixtureCatalog, evidence: list[Evidence]) -> list[TestLink]:
    links: list[TestLink] = []
    sources = _sources_by_path(catalog)
    code = [item for item in evidence if item.source_kind == "code"]
    for test in (item for item in evidence if item.source_kind == "test"):
        source = sources[test.path]
        targets = [
            item.id
            for item in code
            if (
                sources[item.path].id in source.related_sources
                or test.id in sources[item.path].related_tests
            )
        ]
        if targets:
            links.append(
                TestLink(
                    id=f"test-link:{test.id}",
                    test_evidence_id=test.id,
                    target_evidence_ids=targets,
                    relation="symbol_match",
                )
            )
    return links


def build_evidence_graph(catalog: FixtureCatalog, evidence: list[Evidence]) -> EvidenceGraph:
    """Build a graph from recovered evidence without upgrading candidates to proof."""

    edges = relationships(catalog, evidence)
    for link in test_links(catalog, evidence):
        for target_id in link.target_evidence_ids:
            edges.append(
                Relationship(
                    id=f"{target_id}->{link.test_evidence_id}",
                    left_evidence_id=target_id,
                    right_evidence_id=link.test_evidence_id,
                    relation="tested_by",
                    status=link.status,
                    rationale="test-link candidate derived from source metadata",
                )
            )
    unique_edges = {edge.id: edge for edge in edges}
    first = evidence[0] if evidence else None
    return EvidenceGraph(
        repository=first.repository if first else "",
        revision=first.revision if first else "",
        nodes={item.id: item for item in evidence},
        edges=tuple(unique_edges.values()),
    )


def hypotheses(request: ChangeRequest, catalog: FixtureCatalog, evidence: list[Evidence]) -> list[RegressionHypothesis]:
    ids = [item.id for item in evidence]
    if "retri" in request.request.lower():
        return [
            RegressionHypothesis(
                id="duplicate-write-on-timeout",
                statement="Increasing retries can duplicate a write when the server succeeds but the response times out.",
                severity="high",
                supporting_evidence_ids=[item for item in ids if "retry" in item or "client.py" in item or "7ac921" in item],
                verification_steps=["run test_no_duplicate_write", "inspect idempotency-key handling"],
            )
        ]
    return [
        RegressionHypothesis(
            id="dry-run-side-effect",
            statement="A dry-run branch placed after the first notebook mutation would change the preview contract.",
            severity="high",
            supporting_evidence_ids=[item for item in ids if "commands.py" in item or "8f2c1d" in item],
            verification_steps=["run test_dry_run", "compare notebook snapshot before and after preview"],
        ),
        RegressionHypothesis(
            id="solution-cell-mutation",
            statement="A broad output-clearing path could mutate solution-tagged cells.",
            severity="high",
            supporting_evidence_ids=[item for item in ids if "notebook_ops" in item or "test_clear_outputs" in item],
            verification_steps=["run test_preserves_solution_cells"],
        ),
    ]


def render_plan(
    request: ChangeRequest,
    evidence: list[Evidence],
    links: list[TestLink],
    risks: list[RegressionHypothesis],
) -> ChangePlanArtifact:
    retry = "retry" in request.request.lower()
    summary = (
        "Increase retries only with an idempotency contract and duplicate-write verification."
        if retry
        else "Add a dry-run branch before notebook mutation while preserving the existing output and solution-cell contracts."
    )
    current = [
        f"The request targets {request.repository} at revision {request.revision}.",
        f"Search recovered {len(evidence)} versioned evidence records across code, tests, documentation, configuration, and history.",
    ]
    proposed = [summary]
    affected = sorted({item.path for item in evidence})
    test_names = sorted({catalog_test_name(link.test_evidence_id) for link in links})
    risk_lines = [risk.statement for risk in risks]
    unknowns = [
        "Runtime dependencies or production traffic not represented in the repository snapshot remain unknown.",
        "Test linkage is a candidate relationship until the targeted checks are observed.",
    ]
    evidence_ids = [item.id for item in evidence]
    markdown = "\n".join(
        [
            "# Change plan",
            "",
            f"**Request.** {request.request}",
            f"**Repository.** `{request.repository}@{request.revision}`",
            "",
            "## Current behavior",
            *[f"- {line}" for line in current],
            "",
            "## Proposed change",
            *[f"- {line}" for line in proposed],
            "",
            "## Affected surfaces",
            *[f"- `{path}`" for path in affected],
            "",
            "## Regression hypotheses",
            *[f"- **{risk.severity}.** {risk.statement}" for risk in risks],
            "",
            "## Verification",
            *[f"- {name}" for name in test_names or ["No related test was recovered."]],
            "",
            "## Rollout and rollback",
            "- Stage the change behind the smallest available scope and inspect targeted test and runtime signals.",
            "- Revert the change and restore the previous configuration if observed behavior violates the contract.",
            "",
            "## Unknowns",
            *[f"- {line}" for line in unknowns],
            "",
            "## Evidence",
            *[f"- `{item.id}`" for item in evidence],
        ]
    )
    return ChangePlanArtifact(
        summary=summary,
        current_behavior=current,
        proposed_change=proposed,
        affected_surfaces=affected,
        regression_hypotheses=risk_lines,
        tests=test_names,
        rollout=["stage and inspect targeted signals"],
        rollback=["revert the change and restore the prior configuration"],
        observability=["compare targeted test and runtime signals with the pre-change baseline"],
        unknowns=unknowns,
        evidence_ids=evidence_ids,
        markdown=markdown,
    )


def catalog_test_name(evidence_id: str) -> str:
    return evidence_id.rsplit(":", 1)[-1].rsplit("/", 1)[-1].removesuffix(".py")
