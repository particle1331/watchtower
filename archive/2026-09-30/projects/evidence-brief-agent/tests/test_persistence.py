# pyright: reportTypedDictNotRequiredAccess=false

from pathlib import Path

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from evidence_brief.fixtures import request_for
from evidence_brief.workflow import build_evidence_brief_graph, make_context


def test_sqlite_restart_resumes_same_thread(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LANGGRAPH_STRICT_MSGPACK", "true")
    database = tmp_path / "checkpoints.sqlite"
    config: RunnableConfig = {"configurable": {"thread_id": "restart-thread"}}
    context = make_context()
    with SqliteSaver.from_conn_string(str(database)) as saver:
        graph = build_evidence_brief_graph(checkpointer=saver)
        paused = graph.invoke(
            {"request": request_for("conflict-01").model_dump(), "events": [], "branch_results": []},
            config=config,
            context=context,
            version="v2",
        )
        assert paused.interrupts
        assert graph.get_state(config).next == ("review",)
    with SqliteSaver.from_conn_string(str(database)) as saver:
        restarted = build_evidence_brief_graph(checkpointer=saver)
        result = restarted.invoke(
            Command(resume={"action": "approve", "reason": "restart verified"}),
            config=config,
            context=context,
            version="v2",
        )
        assert result.value["status"] == "complete"
        assert len(list(restarted.get_state_history(config))) >= 8
    assert context.controller.effects.count("collect:controlling_text") == 1
    assert context.controller.effects.count("export:artifact") == 1
