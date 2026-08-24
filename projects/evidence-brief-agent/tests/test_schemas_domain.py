from pydantic import ValidationError

from evidence_brief.adapters import ScriptedModelAdapter
from evidence_brief.domain import FixtureCatalog, render_citation, retrieve, verify_claim
from evidence_brief.fixtures import load_corpus, request_for
from evidence_brief.schemas import BriefRequest


def test_boundary_models_reject_unknown_fields() -> None:
    try:
        BriefRequest(question_id="x", question="q", unknown=True)  # type: ignore[call-arg]
    except ValidationError:
        pass
    else:
        raise AssertionError("extra fields must fail validation")


def test_retrieval_preserves_offsets_and_provenance() -> None:
    model = ScriptedModelAdapter()
    catalog = FixtureCatalog(load_corpus())
    task = model.plan(request_for("conflict-01"))[0]
    passages, observations = retrieve(catalog, task)
    source_by_id = catalog.sources
    assert passages
    assert any(item.status == "matched" for item in observations)
    for passage in passages:
        source = source_by_id[passage.source_id]
        assert source.text[passage.start : passage.end] == passage.text
        for claim in model.extract(passage):
            assert verify_claim(claim, passages)
            assert render_citation(claim).startswith(f"[{source.id}#")
