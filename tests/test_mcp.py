"""MCP publishes the typed HTTP schemas and reports identical domain outcomes."""

import asyncio

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from test_api import author_workspace

from watchtower.mcp import create_mcp
from watchtower.services.content import ContentService


def test_mcp_schemas_services_and_stale_revisions(tmp_path):
    root = author_workspace(tmp_path)
    service = ContentService(root)
    server = create_mcp(root)

    async def exercise():
        tools = {tool.name: tool for tool in await server.list_tools()}
        assert "expected_revision" in tools["update_artifact"].input_schema["properties"]
        assert "ArtifactCreate" in tools["create_artifact"].input_schema["$defs"]
        revision = service.list()["revision"]
        created = await server.call_tool("create_artifact", {"data": {"id": "post/mcp", "kind": "post", "title": "MCP plan", "path": "content/notebooks/posts/mcp.ipynb", "planned": {"content": "An outline"}}, "expected_revision": revision})
        assert not created.is_error
        assert service.inspect("post/mcp")["artifact"]["lifecycle"] == "planned"
        current = service.inspect("post/mcp")["revision"]
        updated = await server.call_tool("update_artifact", {"artifact_id": "post/mcp", "patch": {"tags": [" Attention ", "attention"]}, "expected_revision": current})
        assert not updated.is_error
        assert service.inspect("post/mcp")["artifact"]["tags"] == ["Attention"]
        stale = await server.call_tool("update_artifact", {"artifact_id": "post/mcp", "patch": {"title": "Stale title"}, "expected_revision": current})
        assert stale.structured_content["status"] == 412
        assert service.inspect("post/mcp")["artifact"]["title"] == "MCP plan"

    asyncio.run(exercise())


def test_mcp_photo_rows_share_schema_and_service(tmp_path):
    root = author_workspace(tmp_path)
    service = ContentService(root)
    service.create({"id": "gallery/photos", "kind": "gallery", "title": "Photos", "path": "content/data/photos.yaml"})
    image = root / "content/assets/photo.svg"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    server = create_mcp(root)

    async def exercise():
        tools = {tool.name: tool for tool in await server.list_tools()}
        definitions = tools["update_gallery"].input_schema["$defs"]
        assert "lifecycle" not in definitions["GalleryUpdate"]["properties"]
        assert "heading" in definitions["Photo"]["required"]
        assert definitions["Photo"]["properties"]["lifecycle"]["default"] == "draft"
        revision = service.read_data("photos")["revision"]
        saved = await server.call_tool("update_gallery", {"payload": {"photos": [{"heading": "A headed photo", "path": "content/assets/photo.svg", "caption": "A caption"}]}, "expected_revision": revision})
        assert not saved.is_error
        assert service.read_data("photos")["data"]["photos"][0]["lifecycle"] == "draft"
        with pytest.raises(ToolError, match="heading"):
            await server.call_tool("update_gallery", {"payload": {"photos": [{"path": "content/assets/photo.svg", "caption": "A caption"}]}})
        assert service.read_data("photos")["data"]["photos"][0]["heading"] == "A headed photo"

    asyncio.run(exercise())
