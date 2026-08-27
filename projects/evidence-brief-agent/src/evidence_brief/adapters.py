"""Offline legal-research model and an explicitly opt-in live adapter."""

import json
from collections.abc import Sequence
from typing import Any, Protocol

from evidence_brief.schemas import (
    BriefArtifact,
    BriefRequest,
    Claim,
    Contradiction,
    LegalRole,
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
                id="controlling_text",
                query="judicial power grave abuse certiorari jurisdiction adequate remedy filing period sixty days",
                source_tags=["constitutional", "rule"],
                expected_claim_types=["constitutional_text", "rule_text"],
            ),
            ResearchTask(
                id="general_rule",
                query="certiorari substitute appeal grave abuse jurisdiction remedy",
                source_tags=["general-rule"],
                expected_claim_types=["holding"],
            ),
            ResearchTask(
                id="exceptions",
                query="exception substantial justice due process plain speedy adequate remedy",
                source_tags=["exception"],
                expected_claim_types=["exception"],
            ),
        ]

    def extract(self, passage: Passage) -> list[Claim]:
        rules: dict[str, list[tuple[str, str, str, str, str, LegalRole]]] = {
            "constitution-art-viii": [
                ("grave abuse", "judicial_review", "grave_abuse_review", "constitutional", "Judicial power includes review of grave abuse amounting to lack or excess of jurisdiction.", "constitutional_text"),
            ],
            "rule-65-certiorari": [
                ("certiorari addresses", "certiorari", "jurisdictional_defect", "required", "Rule 65 addresses lack or excess of jurisdiction and grave abuse of discretion.", "rule_text"),
                ("petitioner must lack", "certiorari", "adequate_remedy", "none", "The petitioner must lack an appeal or another plain, speedy, and adequate remedy.", "rule_text"),
                ("sixty days", "certiorari", "filing_period", "sixty_days", "The petition ordinarily must be filed within sixty days from notice of the challenged judgment, order, or resolution.", "rule_text"),
            ],
            "gsis-board-v-ca-2018": [
                ("cannot replace", "certiorari", "substitute_for_appeal", "no", "Certiorari is an independent action and ordinarily cannot replace a lost appeal.", "holding"),
                ("substantiate", "certiorari", "exceptions", "must_be_substantiated", "A party invoking a recognized exception must establish facts that justify departing from the general rule.", "exception"),
            ],
            "punongbayan-v-people-2018": [
                ("treated", "certiorari", "treated_as_appeal", "exceptionally", "The Court exceptionally treated a certiorari petition as an appeal where it was timely and substantial justice warranted review.", "exception"),
            ],
            "ortigas-v-ca-2024": [
                ("identifies", "certiorari", "adequate_remedy", "context_dependent", "Certiorari may remain available when the ordinary appeal is not a plain, speedy, and adequate remedy, including a properly supported denial-of-due-process claim.", "exception"),
            ],
        }
        output: list[Claim] = []
        for index, (needle, subject, predicate, value, text, legal_role) in enumerate(rules.get(passage.source_id, []), 1):
            if needle not in passage.text.lower():
                continue
            output.append(
                Claim(
                    id=f"{passage.source_id}-c{index}",
                    subject=subject,
                    predicate=predicate,
                    value=value,
                    text=text,
                    kind="evidence",
                    legal_role=legal_role,
                    authority_citation=passage.citation,
                    official_url=passage.official_url,
                    passage_id=passage.id,
                    source_id=passage.source_id,
                    uncertainty="none",
                )
            )
        return output

    def reconcile(self, claims: Sequence[Claim]) -> list[Contradiction]:
        general_rule = [claim for claim in claims if claim.predicate == "substitute_for_appeal"]
        exceptions = [claim for claim in claims if claim.legal_role == "exception"]
        if general_rule and exceptions:
            return [
                Contradiction(
                    id="appeal-exception-tension",
                    claim_ids=[claim.id for claim in [*general_rule, *exceptions]],
                    subject="general no-substitute rule and narrow exceptions",
                    resolution="Apply the general rule first, then test each claimed exception against its facts and authority.",
                )
            ]
        return []

    def draft(
        self,
        request: BriefRequest,
        claims: Sequence[Claim],
        contradictions: Sequence[Contradiction],
    ) -> BriefArtifact:
        facts = request.facts
        if not facts.record_complete:
            recommendation = "insufficient_authority"
        elif not facts.grave_abuse_supported:
            recommendation = "not_available_on_record"
        elif facts.adequate_appeal_available and facts.exception_facts_supported:
            recommendation = "requires_exception_analysis"
        elif facts.adequate_appeal_available:
            recommendation = "not_available_on_record"
        else:
            recommendation = "available_with_conditions"
        cited = [claim for claim in claims if claim.source_id and claim.passage_id]
        citations = []
        for claim in cited:
            assert claim.source_id is not None and claim.passage_id is not None
            citations.append(f"{claim.authority_citation}; fixture {claim.passage_id.split(':', 1)[1]}")
        authority_lines = "\n".join(f"- {claim.text} [{citations[index]}]" for index, claim in enumerate(cited))
        qualification_lines = "\n".join(f"- {item.subject}: {item.resolution}" for item in contradictions)
        short_answer = recommendation.replace("_", " ").capitalize()
        markdown = (
            f"## Question presented\n\n{request.question}\n\n"
            f"## Short answer\n\n**{short_answer}**\n\n"
            f"## Authorities and analysis\n\n{authority_lines or '- No supporting authority was found in the pinned corpus.'}\n\n"
            f"## Qualifications and unresolved issues\n\n{qualification_lines or '- No material qualification was detected.'}\n\n"
            "> Educational fixture only. A qualified Philippine lawyer must verify the authorities and apply them to the complete record."
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
        data = self._json("Create three bounded Philippine legal-research tasks.", request.model_dump())
        return [ResearchTask.model_validate(item) for item in data]

    def extract(self, passage: Passage) -> list[Claim]:
        data = self._json("Extract provenance-preserving claims.", passage.model_dump())
        return [Claim.model_validate(item) for item in data]

    def reconcile(self, claims: Sequence[Claim]) -> list[Contradiction]:
        data = self._json("Reconcile holdings, rules, and exceptions.", [item.model_dump() for item in claims])
        return [Contradiction.model_validate(item) for item in data]

    def draft(
        self,
        request: BriefRequest,
        claims: Sequence[Claim],
        contradictions: Sequence[Contradiction],
    ) -> BriefArtifact:
        data = self._json(
            "Draft a concise Philippine legal research memorandum with an educational-use disclaimer.",
            {
                "request": request.model_dump(),
                "claims": [item.model_dump() for item in claims],
                "contradictions": [item.model_dump() for item in contradictions],
            },
        )
        return BriefArtifact.model_validate(data)
