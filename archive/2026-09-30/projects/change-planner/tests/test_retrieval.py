from change_planner.fixtures import load_sources
from change_planner.retrieval import FixtureCatalog, agentic_search, hybrid_search, search


def test_search_returns_revisioned_evidence_with_retrieval_trace() -> None:
    catalog = FixtureCatalog(load_sources())
    results = search(catalog, "dry run clear outputs", source_kinds=["code"], method="lexical")

    assert results
    assert results[0].path == "src/change_cli/commands.py"
    assert results[0].revision == "8f2c1d"
    assert results[0].retrieval[0].method == "lexical"
    assert results[0].start_line == 1


def test_hybrid_search_preserves_multiple_retrieval_observations() -> None:
    catalog = FixtureCatalog(load_sources())
    results = hybrid_search(catalog, "timeout retry duplicate write", top_k=3)

    methods = {hit.method for item in results for hit in item.retrieval}
    assert methods == {"dense", "lexical", "structural"}


def test_agentic_search_keeps_a_bounded_refinement_trace() -> None:
    catalog = FixtureCatalog(load_sources())
    results = agentic_search(catalog, "timeout retry duplicate write", top_k=3)

    assert results
    assert len(results) <= 3
    assert all(item.retrieval[0].method == "agentic" for item in results)
    assert [item.retrieval[0].rank for item in results] == [1, 2, 3][: len(results)]
