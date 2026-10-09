"""Authoring forms for posts, portfolio entries, courses and chapters.

Creation and editing share one field model. Every control is a path into an
artifact-shaped record (``field:["planned", "content"]``), so ``apply_fields``
reads submitted values back the same way for both, and the planning catalog in
``watchtower.planning`` decides which fields exist, what they are called and
which ones are recommended to start a draft.
"""
from __future__ import annotations

import copy
import json
import shlex
from typing import Any

from watchtower import planning

KINDS = ("post", "portfolio", "course", "chapter")

SECTIONS = {
    "basics": ("Basics", "What it is and where it lives."),
    "plan": ("Plan", "What you will write. Starting a draft turns each filled field into an editable notebook section."),
    "page": ("Page", "What readers see around the body: the short description, images, tags and related content."),
    "notes": ("Internal notes", "Research, decisions and open questions. Never shown on the site. Track next steps as Kanban cards."),
}

def plan_path(kind: str, key: str) -> list[str]:
    """Record path of a planning field, matching services.content storage."""
    if kind == "post":
        return ["planned", key]
    if kind == "portfolio":
        return ["detail", "planned", key]
    if kind == "course":
        return ["contract", key] if key in {"purpose", "audience"} else ["contract", "planned", key]
    if kind == "chapter":
        return ["plan", key]
    raise ValueError(f"{kind} has no planning fields")


def summary_path(kind: str) -> list[str]:
    """Record path of the one public sentence for a kind."""
    if kind in {"post", "course"}:
        return ["description"]
    if kind == "portfolio":
        return ["detail", "abstract"]
    return ["plan", "summary"]


def ensure_shape(kind: str, record: dict[str, Any]) -> dict[str, Any]:
    """Create every container and leaf the form addresses, so submitted paths always resolve."""
    record = copy.deepcopy(record)
    record.setdefault("title", "")
    record.setdefault("tags", [])
    record.setdefault("relations", [])
    record.setdefault("internal_notes", "")
    for key in ("name", "parent", "section", "toc_title"):
        record.setdefault(key, "")
    if kind not in KINDS:
        return record
    for path in [summary_path(kind), *(plan_path(kind, field.key) for field in planning.PLAN[kind])]:
        node = record
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node.setdefault(path[-1], "")
    if kind == "portfolio":
        detail = record.setdefault("detail", {})
        for key in ("figure_path", "figure_caption", "project_path", "notebook_path"):
            detail.setdefault(key, "")
    if kind == "course":
        record.setdefault("cover", "")
    return record


def creation_record(kind: str) -> dict[str, Any]:
    """Blank record used to render and read back the creation form."""
    return ensure_shape(kind, {"kind": kind})


def _field(path: list[str], value: Any, caption: str, *, long: str = "", core: bool = False, required: bool = False, type: str | None = None, hint: str = "", choices: list[tuple[Any, ...]] | None = None, options: list[str] | None = None, attr: str = "") -> dict[str, Any]:
    field: dict[str, Any] = {
        "name": json.dumps(path),
        "label": " / ".join(path),
        "caption": caption,
        # List values are edited one per line; apply_fields splits them back into lists.
        "value": "\n".join(str(item) for item in value) if isinstance(value, list) else value if value is not None else "",
        "type": type or ("lines" if isinstance(value, list) else "text"),
        "core": core,
        "required": required,
    }
    if long:
        field["prompt"] = long
    if hint:
        field["hint"] = hint
    if choices is not None:
        field["choices"] = choices
        field["type"] = "select"
    if options is not None:
        field["options"] = options
    if attr:
        field["attr"] = attr
    return field


def _get(record: dict[str, Any], path: list[str]) -> Any:
    node: Any = record
    for key in path:
        node = node.get(key) if isinstance(node, dict) else None
    return node


def sections(kind: str, record: dict[str, Any], *, creating: bool = False, courses: list[dict[str, Any]] | None = None, lifecycle_options: list[str] | None = None) -> list[dict[str, Any]]:
    """Intent-based sections for one authoring form, in reading order.

    ``record`` must already have ``ensure_shape`` applied. ``courses`` lists
    ``{"id", "title", "sections": [{"id", "title"}]}`` for chapter placement.
    """
    def value(path: list[str]) -> Any:
        return _get(record, path)

    basics: list[dict[str, Any]] = [_field(["title"], value(["title"]), "Title", required=True)]
    if creating:
        basics.append(_field(["name"], value(["name"]), "Name (optional)", attr="data-name-input", hint="Leave blank to use the title. This sets the permanent URL; spaces become hyphens."))
    if kind == "chapter":
        if creating:
            choices = [(course["id"], course["title"]) for course in courses or []]
            basics.append(_field(["parent"], value(["parent"]), "Course", required=True, choices=[("", "Choose a course"), *choices], attr="data-course-select"))
            section_choices = [(section["id"], section["title"] or section["id"], course["id"]) for course in courses or [] for section in course["sections"]]
            basics.append(_field(["section"], value(["section"]), "Course section", required=True, choices=[("", "Choose a section"), *section_choices], attr="data-section-select"))
        else:
            course_sections = next((course["sections"] for course in courses or [] if course["id"] == record.get("parent")), [])
            basics.append(_field(["section"], value(["section"]), "Course section", choices=[(s["id"], s["title"] or s["id"]) for s in course_sections]))
        basics.append(_field(["toc_title"], value(["toc_title"]), "Short TOC title", hint="Optional navigation label. Defaults to the title."))

    plan: list[dict[str, Any]] = []
    for field in planning.PLAN.get(kind, ()):
        path = plan_path(kind, field.key)
        plan.append(_field(path, value(path), field.label, long=field.prompt, core=field.core))
    plan.sort(key=lambda item: not item["core"])

    page: list[dict[str, Any]] = []
    summary = planning.SUMMARY.get(kind)
    if summary is not None:
        path = summary_path(kind)
        page.append({**_field(path, value(path), summary.label, long=summary.prompt, hint="Optional while planning. Add a linked Kanban task to write this later."), "summary_kind": kind})
    if kind == "course" and not creating:
        page.append(_field(["cover"], value(["cover"]), "Card image", type="featured", hint=""))
    if kind == "portfolio" and not creating:
        page.append(_field(["detail", "figure_path"], value(["detail", "figure_path"]), "Featured image", type="featured", hint="Publishing requires an image."))
        page.append(_field(["detail", "figure_caption"], value(["detail", "figure_caption"]), "Figure caption", hint="Shown beneath the featured image."))
        page.append(_field(["detail", "project_path"], value(["detail", "project_path"]), "Code location", hint="Where the code lives: projects/<name> or archive/<date>/projects/<name>. Defaults to projects/<name>."))
    page.append(_field(["tags"], value(["tags"]), "Tags", hint="One tag per line."))
    page.append(_field(["relations"], value(["relations"]), "Related content"))
    if not creating:
        page.append(_field(["date"], value(["date"]), "Date", hint="Defaults to the creation day in the site timezone."))
        page.append(_field(["visibility"], value(["visibility"]), "Visibility", type="visibility", choices=[("public", "Public"), ("private", "Private")]))
        if lifecycle_options:
            page.append(_field(["lifecycle"], value(["lifecycle"]), "Status", type="lifecycle", options=lifecycle_options))

    notes = [_field(["internal_notes"], value(["internal_notes"]), "Internal notes", long=planning.INTERNAL_NOTES.prompt)]

    result = [
        {"id": "basics", "title": SECTIONS["basics"][0], "explain": SECTIONS["basics"][1], "fields": basics},
        {"id": "plan", "title": SECTIONS["plan"][0], "explain": SECTIONS["plan"][1], "fields": plan},
        {"id": "page", "title": SECTIONS["page"][0], "explain": SECTIONS["page"][1], "fields": page},
    ]
    if not plan:
        # Kinds without a writing brief (personal notebooks, projects) keep only the other sections.
        result = [item for item in result if item["id"] != "plan"]
    result.append({"id": "notes", "title": SECTIONS["notes"][0], "explain": SECTIONS["notes"][1], "fields": notes})
    return result


def creation_plan(kind: str, record: dict[str, Any]) -> dict[str, Any]:
    """Canonical plan values from a submitted record, for planning.plan_patch."""
    values = {field.key: _get(record, plan_path(kind, field.key)) or "" for field in planning.PLAN.get(kind, ())}
    values["summary"] = _get(record, summary_path(kind)) or ""
    values["internal_notes"] = record.get("internal_notes") or ""
    return values


def summary_task(plan: dict[str, Any]) -> dict[str, Any]:
    """A linked task with a saved brief and commands to retrieve current context."""
    kind, identifier = plan["kind"], plan["id"]
    label = "abstract" if kind == "portfolio" else "summary"
    length = "at most 80 words" if kind == "portfolio" else "one or two sentences"
    target = shlex.quote(identifier)
    description = (
        f"Summary task for {identifier}.\n\n"
        f"Write the public {label} for {plan['title']} in {length}. "
        "Use only supported facts; ask for missing context instead of inventing details. "
        "Keep internal notes out of the public text.\n\n"
        "Read the latest context from the repository root before writing:\n"
        f".venv/bin/wt plan {target}\n.venv/bin/wt context {target}\n\n"
        f"Save the result with .venv/bin/wt update {target} --summary <text> "
        "--expected-revision <revision from wt plan>, then read the plan again to verify it. "
        "Keep the artifact's lifecycle and visibility unchanged.\n\n"
        "Saved brief when this task was created:\n\n" + plan["build_brief"]
    )
    return {"title": f"Write {label}: {plan['title']}", "description": description,
            "column": "todo", "artifact_ids": [identifier]}


def tags_from(value: Any) -> list[str]:
    if isinstance(value, str):
        value = value.splitlines()
    result: list[str] = []
    for item in value or []:
        for part in str(item).replace(",", "\n").splitlines():
            part = part.strip()
            if part and part.casefold() not in {tag.casefold() for tag in result}:
                result.append(part)
    return result
