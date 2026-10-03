"""Validated publishing records and shared lifecycle/rendering rules."""
from __future__ import annotations

import re
from datetime import date as Date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import nbformat
from markdown_it import MarkdownIt
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


def relative_path(value: str) -> str:
    path = Path(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("expected a safe repository-relative path")
    return path.as_posix()


class Artifact(Record):
    id: str = Field(min_length=1)
    kind: Literal["post", "course", "chapter", "portfolio", "project", "personal", "gallery"]
    title: str = Field(min_length=1)
    path: str | None = None
    visibility: Literal["public", "private"] = "public"
    lifecycle: Literal["planned", "draft", "published"] = "planned"
    relations: list[str] = Field(default_factory=list)
    date: Date | None = None
    description: str | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    cover: str | None = None
    planned: dict[str, Any] = Field(default_factory=dict)
    parent: str | None = None
    toc_title: str | None = None
    section: str | None = None
    route: str | None = None

    @staticmethod
    def normalize_labels(value: Any) -> Any:
        """Accept legacy categories as tags without keeping two taxonomies."""
        if isinstance(value, dict):
            tags, categories = value.get("tags", []), value.get("categories", [])
            if isinstance(tags, list) and isinstance(categories, list) and all(isinstance(label, str) for label in tags + categories):
                return {**value, "tags": Artifact.clean_tags(tags + categories), "categories": []}
        return value

    @model_validator(mode="before")
    @classmethod
    def categories_are_tags(cls, value: Any) -> Any:
        return cls.normalize_labels(value)

    @field_validator("path", "cover", "route")
    @classmethod
    def safe_paths(cls, value: str | None) -> str | None:
        return relative_path(value) if value is not None else None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            tag = tag.strip()
            if not tag:
                raise ValueError("tags must be nonempty strings")
            if tag.casefold() not in seen:
                result.append(tag)
                seen.add(tag.casefold())
        return result

    @model_validator(mode="after")
    def variant(self) -> Artifact:
        if self.kind == "chapter" and not all((self.parent, self.toc_title, self.section)):
            raise ValueError("chapter requires parent, toc_title, and section")
        if self.kind != "portfolio" and self.path is None:
            raise ValueError(f"{self.kind} requires path")
        if self.kind in {"post", "personal", "chapter"} and (not self.path or not self.path.startswith("content/notebooks/") or not self.path.endswith(".ipynb")):
            raise ValueError("notebook sources must be .ipynb under content/notebooks/")
        if self.kind == "course" and (not self.path or not self.path.startswith("content/notebooks/courses/")):
            raise ValueError("course directory must be under content/notebooks/courses/")
        if self.kind == "project" and (not self.path or not self.path.startswith("projects/")):
            raise ValueError("active project path must be under projects/")
        if self.kind == "gallery" and self.path != "content/data/photos.yaml":
            raise ValueError("gallery path must be content/data/photos.yaml")
        return self


class Catalog(Record):
    version: Literal[1] = 1
    artifacts: list[Artifact]
    retired_ids: list[str] = Field(default_factory=list)
    retired_sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def reserved_names(self) -> Catalog:
        retired = {value.casefold() for value in self.retired_ids}
        sources = {relative_path(value).casefold() for value in self.retired_sources}
        for artifact in self.artifacts:
            if artifact.id.casefold() in retired:
                raise ValueError(f"ID was previously deleted and remains reserved: {artifact.id}")
            if artifact.path and artifact.path.casefold() in sources:
                raise ValueError(f"source was previously deleted and remains reserved: {artifact.path}")
        return self


class PortfolioEntry(Record):
    id: str
    abstract: str | None = None
    figure_path: str | None = None
    figure_caption: str | None = None
    notebook_path: str | None = None
    project_name: str | None = None
    project_source: Literal["active", "archived"] = "active"
    archive_date: Date | None = None
    planned: dict[str, str] = Field(default_factory=dict)

    @field_validator("figure_path", "notebook_path")
    @classmethod
    def safe_paths(cls, value: str | None) -> str | None:
        return relative_path(value) if value is not None else None

    @field_validator("project_name")
    @classmethod
    def safe_name(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
            raise ValueError("project_name must be a single folder name")
        return value

    @model_validator(mode="after")
    def reference(self) -> PortfolioEntry:
        if self.project_source == "archived" and self.archive_date is None:
            raise ValueError("archived source requires archive_date")
        if self.project_source == "active" and self.archive_date is not None:
            raise ValueError("active source forbids archive_date")
        if self.notebook_path and (not self.notebook_path.startswith("content/notebooks/portfolio/") or not self.notebook_path.endswith(".ipynb")):
            raise ValueError("portfolio notebook must be under content/notebooks/portfolio/")
        return self

    @property
    def project_path(self) -> str | None:
        if self.project_name is None:
            return None
        prefix = f"archive/{self.archive_date}/projects" if self.project_source == "archived" else "projects"
        return f"{prefix}/{self.project_name}"


class Portfolio(Record):
    version: Literal[1] = 1
    entries: list[PortfolioEntry] = Field(default_factory=list)


class Section(Record):
    id: str = Field(min_length=1)
    title: str
    chapters: list[str] = Field(default_factory=list)


class ChapterPlan(Record):
    chapter_id: str
    section: str
    summary: str | None = None
    content: str = ""
    lab_and_evidence: str = ""


class CourseContract(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    purpose: str
    audience: str
    planned: dict[str, Any]
    actualized: dict[str, Any]
    overview: str | None = None
    toc: list[Section]


class Contact(Record):
    phone: str
    email: str
    github: str
    linkedin: str


class Employment(Record):
    title: str
    company: str
    dates: str
    bullets: list[str]
    tech: str | None = None


class SkillGroup(Record):
    name: str
    entries: list[str]


class Education(Record):
    institution: str
    degree: str
    dates: str
    major: str | None = None
    awards: str | None = None
    thesis: str | None = None
    courses: list[str] | None = None
    description: str | None = None


class ResumeProject(Record):
    title: str
    bullets: list[str]
    artifact_id: str | None = None


class Profile(Record):
    version: Literal[1] = 1
    name: str
    contact: Contact
    summary: str
    homepage_intro: list[str]
    employment: list[Employment]
    early_employment: list[Employment] = Field(default_factory=list)
    skills: list[SkillGroup]
    education: list[Education]
    projects: list[ResumeProject] = Field(default_factory=list)


class Photo(Record):
    heading: str = Field(min_length=1)
    path: str = ""
    caption: str
    lifecycle: Literal["draft", "published"] = "draft"
    width: str | None = None

    @field_validator("width")
    @classmethod
    def percentage_width(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip()
        if not re.fullmatch(r"(?:\d+(?:\.\d+)?|\.\d+)%", value) or not 0 < float(value[:-1]) <= 100:
            raise ValueError("photo width must be a percentage greater than 0 and at most 100%, e.g. 80%; leave blank for default size")
        return value

    @field_validator("heading")
    @classmethod
    def section_heading(cls, value: str) -> str:
        if not value.strip() or "\n" in value or "\r" in value:
            raise ValueError("photo heading must be nonempty and on one line")
        return value.strip()

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        value = value.strip()
        return relative_path(value) if value else ""

    @model_validator(mode="after")
    def published_image(self) -> Photo:
        if self.lifecycle == "published" and not self.path:
            raise ValueError("Published photos need an image. Upload a photo before publishing.")
        return self


class Photos(Record):
    version: Literal[1] = 1
    photos: list[Photo] = Field(default_factory=list)


class SiteSettings(Record):
    version: Literal[1] = 1
    repository_url: str = "https://github.com/particle1331/watchtower"
    source_ref: str = "main"
    timezone: str = "Asia/Manila"
    quarto: dict[str, Any] = Field(default_factory=dict)

    @field_validator("repository_url")
    @classmethod
    def repository(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme != "https" or parsed.netloc != "github.com" or not re.fullmatch(r"/[\w.-]+/[\w.-]+/?", parsed.path) or parsed.query or parsed.fragment:
            raise ValueError("repository_url must be an HTTPS GitHub owner/repository URL")
        return value.rstrip("/")

    @field_validator("source_ref")
    @classmethod
    def ref(cls, value: str) -> str:
        if not value.strip() or any(c in value for c in "?#\\") or ".." in value.split("/"):
            raise ValueError("invalid source ref")
        return value

    @field_validator("timezone")
    @classmethod
    def zone(cls, value: str) -> str:
        ZoneInfo(value)
        return value


KanbanColumn = Literal["todo", "in-progress", "review", "done"]
KANBAN_COLUMNS = [("todo", "To do"), ("in-progress", "In progress"), ("review", "Review"), ("done", "Done")]


class KanbanCard(Record):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$", max_length=100)
    ref: str | None = Field(default=None, pattern=r"^card#[1-9][0-9]*$")
    title: str = Field(min_length=1)
    description: str = ""
    column: KanbanColumn = "todo"
    artifact_ids: list[str] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def nonempty_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("card title must not be blank")
        return value.strip()

    @field_validator("artifact_ids")
    @classmethod
    def linked_ids(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("linked stable IDs must not be blank")
        return list(dict.fromkeys(value.strip() for value in values))


class Kanban(Record):
    version: Literal[1] = 1
    cards: list[KanbanCard] = Field(default_factory=list)
    next_number: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def unique_cards(self) -> Kanban:
        if len({card.id for card in self.cards}) != len(self.cards):
            raise ValueError("duplicate Kanban card IDs")
        refs = [card.ref for card in self.cards if card.ref is not None]
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate Kanban card references")
        return self


class Workspace(Record):
    artifacts: list[Artifact]
    portfolio: list[PortfolioEntry]
    courses: dict[str, CourseContract]
    profile: Profile
    photos: list[Photo]
    settings: SiteSettings
    kanban: list[KanbanCard] = Field(default_factory=list)


def eligible(artifact: Artifact, artifacts: list[Artifact], mode: str = "production") -> bool:
    if artifact.kind == "project":
        return False
    if mode == "preview":
        return True
    if artifact.visibility != "public" or artifact.lifecycle == "draft":
        return False
    if artifact.kind == "chapter":
        parent = next((a for a in artifacts if a.id == artifact.parent), None)
        if parent is None or parent.visibility != "public" or parent.lifecycle == "draft":
            return False
        if artifact.lifecycle == "published" and parent.lifecycle != "published":
            return False
    return True


def source_path(artifact: Artifact, state: Workspace) -> str | None:
    if artifact.kind == "portfolio":
        detail = next((p for p in state.portfolio if p.id == artifact.id), None)
        return detail.notebook_path if detail else None
    if artifact.kind == "course":
        return f"{artifact.path}/index.ipynb"
    if artifact.kind in {"gallery", "project"}:
        return None
    return artifact.path


def route_for(artifact: Artifact) -> str:
    if artifact.route:
        return artifact.route
    if artifact.kind == "portfolio":
        return f"nb/portfolio/{artifact.id.split('/')[-1]}.ipynb"
    if artifact.kind == "gallery":
        return "gallery.qmd"
    path = str(artifact.path).replace("content/notebooks/", "nb/", 1)
    return f"{path}/index.ipynb" if artifact.kind == "course" else path


def source_url(detail: PortfolioEntry, settings: SiteSettings, *, reserved_name: str | None = None) -> str | None:
    project_path = detail.project_path
    if project_path is None and reserved_name and detail.project_source == "active":
        project_path = f"projects/{reserved_name}"
    if project_path is None:
        return None
    path = "/".join(quote(part, safe="") for part in project_path.split("/"))
    return f"{settings.repository_url}/tree/{quote(settings.source_ref, safe='')}/{path}"


def markdown_h1s(source: str) -> list[str]:
    tokens = MarkdownIt().parse(source)
    return [displayed_text(tokens[i + 1]) for i, token in enumerate(tokens) if token.type == "heading_open" and token.tag == "h1"]


def displayed_text(token: Any) -> str:
    return "".join(child.content for child in token.children or [] if child.type in {"text", "code_inline", "image"}) if token.children else token.content


def h1s(notebook: nbformat.NotebookNode) -> list[str]:
    return [title for cell in notebook.cells if cell.cell_type == "markdown" for title in markdown_h1s(cell.source)]


def has_content(notebook: nbformat.NotebookNode, chapter_title: str | None = None) -> bool:
    for cell in notebook.cells:
        if cell.get("outputs") or cell.get("attachments"):
            return True
        source = cell.source.strip()
        if cell.cell_type == "markdown" and chapter_title:
            tokens = MarkdownIt().parse(source)
            ignored: set[int] = set()
            for i, token in enumerate(tokens):
                if token.type == "heading_open" and token.tag == "h1" and displayed_text(tokens[i + 1]) == chapter_title and token.map:
                    ignored.update(range(*token.map))
            source = "\n".join(line for i, line in enumerate(source.splitlines()) if i not in ignored).strip()
        if source:
            return True
    return False


def plan_body(artifact: Artifact, state: Workspace) -> str:
    if artifact.kind == "chapter":
        course = state.courses[str(artifact.parent)]
        plan = next((p for p in course.planned.get("chapters", []) if p.get("chapter_id") == artifact.id), {})
        return f"# {artifact.title}\n\n## Planned content\n\n{plan.get('content', '')}\n\n## Planned lab and evidence\n\n{plan.get('lab_and_evidence', '')}"
    if artifact.kind == "portfolio":
        detail = next(p for p in state.portfolio if p.id == artifact.id)
        plan = detail.planned
        body = f"[← Portfolio](/portfolio.html)\n\n{plan.get('introduction', '')}\n\n## What it contains\n\n{plan.get('what_it_contains', '')}\n\n## Explore the project\n\n"
        links = []
        reserved = artifact.lifecycle == "planned" and detail.project_source == "active"
        url = source_url(detail, state.settings, reserved_name=artifact.id.split("/")[-1] if reserved else None)
        if url:
            source_label = "Reserved source code" if reserved else "Archived source" if detail.project_source == "archived" else "Source"
            links.append(f"- [{source_label}]({url})")
        for related in state.artifacts:
            if related.id in artifact.relations and eligible(related, state.artifacts):
                links.append(f"- [{related.title}](/{Path(route_for(related)).with_suffix('.html').as_posix()})")
        if links:
            body += "Related content:\n\n" + "\n".join(links) + "\n\n"
        return body + plan.get("scope_notes", "")
    if artifact.kind == "course":
        course = state.courses[artifact.id]
        return f"{course.purpose}\n\n{course.audience}\n\n{course.planned.get('summary', '')}"
    return str(artifact.planned.get("content", artifact.description or ""))
