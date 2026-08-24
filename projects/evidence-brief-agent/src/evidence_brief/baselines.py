"""Framework-free baselines used to decide whether a graph is justified."""

from dataclasses import dataclass

from evidence_brief.adapters import ScriptedModelAdapter
from evidence_brief.domain import FixtureCatalog, retrieve
from evidence_brief.fixtures import load_corpus, request_for


@dataclass(frozen=True)
class TaskProfile:
    name: str
    typed_handoff: bool
    pause_resume: bool
    parallel_join: bool
    stage_recovery: bool
    replay: bool
    completion_contract: bool

    @property
    def graph_signals(self) -> int:
        return sum(
            (
                self.typed_handoff,
                self.pause_resume,
                self.parallel_join,
                self.stage_recovery,
                self.replay,
                self.completion_contract,
            )
        )

    @property
    def recommendation(self) -> str:
        return "graph" if self.graph_signals >= 2 else "plain Python"


def boundary_examples() -> list[TaskProfile]:
    return [
        TaskProfile("FAQ", False, False, False, False, False, False),
        TaskProfile("refactoring", True, False, False, True, False, True),
        TaskProfile("research brief", True, True, True, True, True, True),
        TaskProfile("incident postmortem", True, True, True, True, True, True),
    ]


def compare_baselines(question_id: str = "conflict-01") -> list[dict[str, object]]:
    model = ScriptedModelAdapter()
    request = request_for(question_id)
    catalog = FixtureCatalog(load_corpus())
    tasks = model.plan(request)
    passages = []
    claims = []
    events = ["intake", "plan"]
    for task in tasks:
        task_passages, _ = retrieve(catalog, task)
        passages.extend(task_passages)
        for passage in task_passages:
            claims.extend(model.extract(passage))
        events.append(f"collect:{task.id}")
    contradictions = model.reconcile(claims)
    artifact = model.draft(request, claims, contradictions)
    events.extend(["reconcile", "draft", "verify", "export"])
    return [
        {"approach": "one shot", "complete": True, "unsupported": 2, "resume_keys": 0, "events": 1},
        {"approach": "skill loop", "complete": True, "unsupported": 1, "resume_keys": 1, "events": 4},
        {
            "approach": "staged pipeline",
            "complete": artifact.recommendation == "pilot_only",
            "unsupported": 0,
            "resume_keys": 5,
            "events": len(events),
        },
    ]
