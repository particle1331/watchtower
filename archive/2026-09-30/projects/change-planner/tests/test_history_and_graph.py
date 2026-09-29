import subprocess
from pathlib import Path

from change_planner.analysis import build_evidence_graph
from change_planner.fixtures import load_sources
from change_planner.history import ingest_git_history
from change_planner.retrieval import FixtureCatalog, hybrid_search


def test_git_history_is_searchable_evidence(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test User"], check=True)
    (tmp_path / "service.py").write_text("def deploy():\n    return True\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "service.py"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "Add deploy service"], check=True)

    history = ingest_git_history(tmp_path, repository="fixture/service", paths=["service.py"])

    assert len(history) == 1
    assert history[0].source_kind == "git"
    assert history[0].symbols == ["deploy"]
    assert "service.py" in history[0].related_sources


def test_evidence_graph_keeps_candidate_edges_and_revision() -> None:
    catalog = FixtureCatalog(load_sources())
    evidence = hybrid_search(catalog, "dry run clear outputs", top_k=6)

    graph = build_evidence_graph(catalog, evidence)

    assert graph.repository == "fixture/change-cli"
    assert graph.revision == "8f2c1d"
    assert graph.nodes
    assert graph.edges
    assert all(edge.status == "candidate" for edge in graph.edges)
    assert any(edge.relation == "tested_by" for edge in graph.edges)
