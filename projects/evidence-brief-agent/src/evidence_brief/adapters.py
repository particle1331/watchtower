"""Offline scripted model and an explicitly opt-in live adapter."""

import json
from collections.abc import Sequence
from typing import Any, Protocol

from evidence_brief.schemas import (
    BriefArtifact,
    BriefRequest,
    Claim,
    Contradiction,
    Passage,
    ResearchTask,
)


class ModelAdapter(Protocol):
    def plan(self, request: BriefRequest) -> list[ResearchTask]: ...

    def extract(self, passage: Passage) -> list[Claim]: ...

    def reconcile(self, claims: Sequence[Claim]) -> list[Contradiction]: ...

    def draft(
        self,
        request: BriefRequest,
        claims: Sequence[Claim],
        contradictions: Sequence[Contradiction],
    ) -> BriefArtifact: ...


class ScriptedModelAdapter:
    """Return expected simulated behavior and reject unexpected fixture inputs."""

    def plan(self, request: BriefRequest) -> list[ResearchTask]:
        if not request.question_id:
            raise ValueError("question_id is required in deterministic mode")
        return [
            ResearchTask(
                id="security",
                query="encryption audit residency regulated policy",
                source_tags=["security", "policy", "independent"],
                expected_claim_types=["security", "residency"],
            ),
            ResearchTask(
                id="performance",
                query="recall latency benchmark representative corpus",
                source_tags=["performance", "internal", "vendor"],
                expected_claim_types=["quality", "latency"],
            ),
            ResearchTask(
                id="operations",
                query="indexing recovery capacity production",
                source_tags=["operations", "independent"],
                expected_claim_types=["recovery", "capacity"],
            ),
        ]

    def extract(self, passage: Passage) -> list[Claim]:
        rules = {
            "vendor-security-2026": [
                ("security", "audit_log", "available", "AtlasVector exposes an exportable audit log."),
                ("residency", "eu_available", "yes", "The vendor guide says EU residency is available."),
            ],
            "independent-audit-2026": [
                ("security", "audit_log", "verified", "An independent audit verified audit-log export."),
                ("residency", "eu_available", "no", "The audit found that EU residency was not available."),
            ],
            "internal-benchmark-2026": [
                ("retrieval", "pilot_thresholds", "passed", "Recall and p95 latency passed pilot thresholds."),
            ],
            "operations-review-2026": [
                ("operations", "restart_recovery", "automatic", "Indexing recovered after a worker restart."),
                ("operations", "capacity_test", "required", "A capacity run is recommended before production."),
            ],
            "regulatory-policy-2026": [
                ("policy", "verified_residency", "required", "Regulated production requires verified residency."),
            ],
            "vendor-benchmark-2024": [
                ("retrieval", "p95_latency", "under_100ms", "An outdated vendor benchmark reports sub-100ms p95."),
            ],
        }
        output: list[Claim] = []
        for index, (subject, predicate, value, text) in enumerate(rules.get(passage.source_id, []), 1):
            output.append(
                Claim(
                    id=f"{passage.source_id}-c{index}",
                    subject=subject,
                    predicate=predicate,
                    value=value,
                    text=text,
                    kind="evidence",
                    passage_id=passage.id,
                    source_id=passage.source_id,
                    uncertainty="outdated source" if passage.source_id.endswith("2024") else "none",
                )
            )
        return output

    def reconcile(self, claims: Sequence[Claim]) -> list[Contradiction]:
        residency = [claim for claim in claims if claim.predicate == "eu_available"]
        if {claim.value for claim in residency} == {"yes", "no"}:
            return [
                Contradiction(
                    id="residency-conflict",
                    claim_ids=[claim.id for claim in residency],
                    subject="EU data residency",
                    resolution="Treat residency as unverified until an independent deployment test resolves it.",
                )
            ]
        latency = [claim for claim in claims if claim.predicate in {"p95_latency", "pilot_thresholds"}]
        if len(latency) > 1:
            return [
                Contradiction(
                    id="benchmark-scope-conflict",
                    claim_ids=[claim.id for claim in latency],
                    subject="benchmark representativeness",
                    resolution="Prefer the newer internal representative-corpus result.",
                )
            ]
        return []

    def draft(
        self,
        request: BriefRequest,
        claims: Sequence[Claim],
        contradictions: Sequence[Contradiction],
    ) -> BriefArtifact:
        if request.question_id.startswith("insufficient"):
            recommendation = "insufficient_evidence"
        elif request.question_id.startswith("conflict") or request.question_id in {"scope-02", "scope-03"}:
            recommendation = "pilot_only"
        else:
            recommendation = "adopt_with_controls"
        cited = [claim for claim in claims if claim.source_id and claim.passage_id]
        citations = []
        for claim in cited:
            assert claim.source_id is not None and claim.passage_id is not None
            citations.append(f"{claim.source_id}#{claim.passage_id.split(':', 1)[1]}")
        evidence_lines = "\n".join(f"- {claim.text} [{citations[index]}]" for index, claim in enumerate(cited))
        conflict_lines = "\n".join(f"- {item.subject}: {item.resolution}" for item in contradictions)
        markdown = (
            f"## Recommendation\n\n**{recommendation}** for: {request.question}\n\n"
            f"## Evidence\n\n{evidence_lines or '- No supporting fixture evidence was found.'}\n\n"
            f"## Contradictions and uncertainty\n\n{conflict_lines or '- No material contradiction was detected.'}"
        )
        return BriefArtifact(recommendation=recommendation, markdown=markdown, citations=citations)


class OpenAIModelAdapter:
    """Minimal live adapter; callers must opt in and provide a configured client."""

    def __init__(self, client: Any, model: str = "gpt-5-mini"):
        self.client = client
        self.model = model

    def _json(self, instruction: str, payload: object) -> Any:
        response = self.client.responses.create(
            model=self.model,
            input=f"{instruction}\nReturn JSON only.\n{json.dumps(payload, default=str)}",
        )
        return json.loads(response.output_text)

    def plan(self, request: BriefRequest) -> list[ResearchTask]:
        data = self._json("Create three bounded research tasks.", request.model_dump())
        return [ResearchTask.model_validate(item) for item in data]

    def extract(self, passage: Passage) -> list[Claim]:
        data = self._json("Extract provenance-preserving claims.", passage.model_dump())
        return [Claim.model_validate(item) for item in data]

    def reconcile(self, claims: Sequence[Claim]) -> list[Contradiction]:
        data = self._json("Reconcile direct contradictions.", [item.model_dump() for item in claims])
        return [Contradiction.model_validate(item) for item in data]

    def draft(
        self,
        request: BriefRequest,
        claims: Sequence[Claim],
        contradictions: Sequence[Contradiction],
    ) -> BriefArtifact:
        data = self._json(
            "Draft a concise evidence brief.",
            {
                "request": request.model_dump(),
                "claims": [item.model_dump() for item in claims],
                "contradictions": [item.model_dump() for item in contradictions],
            },
        )
        return BriefArtifact.model_validate(data)
