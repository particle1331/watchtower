"""Control pipelines used to justify graph orchestration."""

from change_planner.adapters import ScriptedModelAdapter
from change_planner.fixtures import case_for, load_sources
from change_planner.retrieval import FixtureCatalog, hybrid_search, search
from change_planner.workflow import run_fixture


def _coverage(paths: set[str], expected: set[str]) -> float:
    return round(len(paths.intersection(expected)) / max(1, len(expected)), 3)


def compare_control_models(scenario_id: str = "dry-run-01") -> list[dict[str, object]]:
    """Compare one direct search, a staged Python planner, and the graph path."""

    case = case_for(scenario_id)
    catalog = FixtureCatalog(load_sources())
    expected = set(case.expected_sources)
    source_ids = {source.path: source.id for source in catalog.sources.values()}

    direct = search(catalog, case.question, method="hybrid", top_k=6)
    direct_paths = {source_ids[item.path] for item in direct}

    staged_ids: set[str] = set()
    staged_events: list[str] = []
    for task in ScriptedModelAdapter().plan(case.request):
        staged_events.append(f"stage:{task.id}")
        staged_ids.update(
            source_ids[item.path]
            for item in hybrid_search(
                catalog,
                task.query,
                source_kinds=task.source_kinds,
                top_k=6,
            )
        )

    graph_state = run_fixture(scenario_id)
    graph_ids = {source_ids[item["path"]] for item in graph_state["evidence"]}
    return [
        {
            "approach": "direct search",
            "evidence_recall": _coverage(direct_paths, expected),
            "events": ["search:single"],
            "parallel": False,
            "resumable": False,
        },
        {
            "approach": "staged Python planner",
            "evidence_recall": _coverage(staged_ids, expected),
            "events": staged_events,
            "parallel": False,
            "resumable": False,
        },
        {
            "approach": "LangGraph workflow",
            "evidence_recall": _coverage(graph_ids, expected),
            "events": graph_state["events"],
            "parallel": "investigate:behavior" in graph_state["events"],
            "resumable": True,
        },
    ]
