"""MCP transport over the same revision-aware services used by HTTP and the CLI.

The official Python MCP SDK 2 renamed FastMCP to MCPServer. Run over stdio so
agent access does not expose an additional network author endpoint.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from mcp.server import MCPServer

from watchtower.api.schemas import (
    ArtifactCreate,
    ArtifactPatch,
    BatchUpdate,
    GalleryUpdate,
    Kind,
    StructuredUpdate,
)
from watchtower.services.build import BuildService
from watchtower.services.content import ContentService
from watchtower.services.workspace import ServiceError


def create_mcp(root: Path | None = None) -> MCPServer:
    content = ContentService((root or Path.cwd()).resolve())
    builds = BuildService((root or Path.cwd()).resolve())
    server = MCPServer("Watchtower", instructions="Manage saved Watchtower content. Read its revision before mutation and pass expected_revision to detect stale edits. Notebook bodies are edited with supported notebook operations, not these metadata tools.")

    def invoke(operation: Callable[..., dict[str, Any]], *args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return operation(*args, **kwargs)
        except ServiceError as error:
            return {"error": error.as_dict(), "status": error.status}

    @server.tool()
    def list_artifacts(kind: Kind | None = None) -> dict[str, Any]:
        """List registered artifacts and a shared workspace revision."""
        return invoke(content.list, kind=kind)

    @server.tool()
    def inspect_artifact(artifact_id: str) -> dict[str, Any]:
        """Inspect metadata, canonical notebook and live-site eligibility."""
        return invoke(content.inspect, artifact_id)

    @server.tool()
    def create_artifact(data: ArtifactCreate, expected_revision: str | None = None) -> dict[str, Any]:
        """Create a registered plan; explicit start materializes authored content."""
        return invoke(content.create, data.model_dump(exclude_none=True), expected_revision=expected_revision)

    @server.tool()
    def update_artifact(artifact_id: str, patch: ArtifactPatch, expected_revision: str | None = None) -> dict[str, Any]:
        """Validate and save a metadata patch, preserving authored notebook cells."""
        return invoke(content.update, artifact_id, patch.model_dump(exclude_unset=True), expected_revision=expected_revision)

    @server.tool()
    def start_artifact(artifact_id: str, expected_revision: str | None = None) -> dict[str, Any]:
        """Materialize a plan as an editable draft without replacing an existing file."""
        return invoke(content.start, artifact_id, expected_revision=expected_revision)

    @server.tool()
    def publish_artifact(artifact_id: str, expected_revision: str | None = None) -> dict[str, Any]:
        """Publish eligible authored content; visibility is preserved."""
        return invoke(content.publish, artifact_id, expected_revision=expected_revision)

    @server.tool()
    def draft_artifact(artifact_id: str, expected_revision: str | None = None) -> dict[str, Any]:
        """Return published content to draft and preserve its notebook."""
        return invoke(content.draft, artifact_id, expected_revision=expected_revision)

    @server.tool()
    def read_data(name: str) -> dict[str, Any]:
        """Read profile, portfolio, photos, settings or course/<slug> structured data."""
        return invoke(content.read_data, name)

    @server.tool()
    def update_data(name: str, payload: StructuredUpdate, expected_revision: str | None = None) -> dict[str, Any]:
        """Save structured fields with the same validation and conflict rules as HTTP."""
        return invoke(content.update_data, name, payload.data, expected_revision=expected_revision)

    @server.tool()
    def update_gallery(payload: GalleryUpdate, expected_revision: str | None = None) -> dict[str, Any]:
        """Save headed photo rows with each photo's draft or published state."""
        data = {"version": 1, "photos": [photo.model_dump() for photo in payload.photos]}
        return invoke(content.update_gallery, data, expected_revision=expected_revision)

    @server.tool()
    def batch_update(payload: BatchUpdate, expected_revision: str | None = None) -> dict[str, Any]:
        """Repair multiple metadata/data records in one fully validated transaction."""
        updates = [update.model_dump(exclude_unset=True) for update in payload.updates]
        return invoke(content.batch, updates, payload.data, expected_revision=expected_revision)

    @server.tool()
    def validate_workspace() -> dict[str, Any]:
        """Verify all saved tracked inputs before rendering."""
        return invoke(content.validate)

    @server.tool()
    def submit_build(mode: Literal["preview", "production"] = "preview") -> dict[str, Any]:
        """Queue a serialized render and return its ID promptly; never execute cells."""
        return invoke(builds.submit, mode=mode)

    @server.tool()
    def get_build(build_id: str) -> dict[str, Any]:
        """Inspect a validated build ID, status and logs."""
        return invoke(builds.get, build_id)

    return server


def main() -> None:
    create_mcp().run(transport="stdio")


if __name__ == "__main__":
    main()
