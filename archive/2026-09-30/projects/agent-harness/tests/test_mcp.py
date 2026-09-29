from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent_harness.mcp.bridge import (
    MCPServerConfig,
    mcp_tool_to_openai_schema,
    namespace_tool_name,
    translate_tool_schema,
)


def test_mcp_schema_translation_is_pure_and_namespaced():
    input_schema = {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    }

    translated = translate_tool_schema("math", "evaluate", "Evaluate an expression", input_schema)
    translated_mapping = mcp_tool_to_openai_schema(
        "math",
        {"name": "evaluate", "description": "Evaluate an expression", "inputSchema": input_schema},
    )
    translated_object = mcp_tool_to_openai_schema(
        "math",
        SimpleNamespace(name="evaluate", description="Evaluate an expression", inputSchema=input_schema),
    )

    assert namespace_tool_name("math", "evaluate") == "math__evaluate"
    assert translated["name"] == "math__evaluate"
    assert translated["parameters"] is input_schema
    assert translated_mapping == translated
    assert translated_object == translated


def test_mcp_server_config_validates_transport_choice():
    assert MCPServerConfig(name="local", command="python").transport_kind == "stdio"
    assert MCPServerConfig(name="remote", url="https://example.test/mcp").transport_kind == "http"
    with pytest.raises(ValueError):
        MCPServerConfig(name="missing")
    with pytest.raises(ValueError):
        MCPServerConfig(name="both", command="python", url="https://example.test")
