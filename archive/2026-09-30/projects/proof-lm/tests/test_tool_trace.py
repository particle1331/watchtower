import pytest
from pydantic import ValidationError

from proof_lm.schemas import TOOL_TRACE_SCHEMA, ToolTrace


def test_no_call_trace_is_valid_without_tool_name() -> None:
    trace = ToolTrace(
        schema_version=TOOL_TRACE_SCHEMA,
        trace_id="trace-v1",
        episode_id="episode-v1",
        step=0,
        checkpoint_id="checkpoint-v1",
        tool_registry_id="registry-v1",
        request="Is P -> P valid?",
        status="no_call",
    )
    assert trace.tool_name is None


def test_error_trace_requires_a_machine_readable_error_code() -> None:
    with pytest.raises(ValidationError, match="error_code"):
        ToolTrace(
            schema_version=TOOL_TRACE_SCHEMA,
            trace_id="trace-v1",
            episode_id="episode-v1",
            step=0,
            checkpoint_id="checkpoint-v1",
            tool_registry_id="registry-v1",
            request="check this proof",
            tool_name="check_proof",
            status="error",
        )
