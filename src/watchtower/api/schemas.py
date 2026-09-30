"""Transport schemas shared by the HTTP and MCP adapters."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from watchtower.models import Artifact, CourseContract, Photo, PortfolioEntry

Kind = Literal["post", "course", "chapter", "portfolio", "project", "personal", "gallery"]


class PortfolioInput(PortfolioEntry):
    id: str = ""


class CourseInput(CourseContract):
    id: str = ""


class ArtifactCreate(Artifact):
    """Common artifact fields; variant fields are validated by the content service."""

    lifecycle: Literal["planned"] = "planned"
    detail: PortfolioInput | None = None
    contract: CourseInput | None = None
    planned_content: str | None = None
    planned_lab_and_evidence: str | None = None

    @model_validator(mode="before")
    @classmethod
    def linked_ids(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = dict(value)
            for field in ("detail", "contract"):
                if isinstance(value.get(field), dict) and not value[field].get("id"):
                    value[field] = {**value[field], "id": value.get("id", "")}
        return value


class ArtifactMetadataPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    description: str | None = None
    visibility: Literal["public", "private"] | None = None
    lifecycle: Literal["planned", "draft", "published"] | None = None
    tags: list[str] | None = None
    categories: list[str] | None = None
    relations: list[str] | None = None
    path: str | None = None
    date: str | None = None
    cover: str | None = None
    planned: dict[str, Any] | None = None
    parent: str | None = None
    toc_title: str | None = None
    section: str | None = None
    route: str | None = None


class ArtifactPatch(ArtifactMetadataPatch):
    detail: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None


class StructuredUpdate(BaseModel):
    data: dict[str, Any]


class GalleryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    photos: list[Photo]


class GalleryState(GalleryUpdate):
    revision: str


class RecordMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    patch: ArtifactMetadataPatch


class BatchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    updates: list[RecordMutation] = Field(default_factory=list)
    data: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BuildRequest(BaseModel):
    mode: Literal["preview", "production"] = "preview"


class ServiceResult(BaseModel):
    """Service results retain variant-specific details in the generated schema."""

    model_config = ConfigDict(extra="allow")
    revision: str | None = None


class ArtifactList(ServiceResult):
    artifacts: list[dict[str, Any]]


class ArtifactResult(ServiceResult):
    artifact: dict[str, Any]


class DataResult(ServiceResult):
    data: dict[str, Any]
