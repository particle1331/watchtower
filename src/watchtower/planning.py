"""Authoring fields shared by the CMS, CLI, draft seeding and the build brief.

Every planning field is defined once here:

- ``PLAN`` is the writing brief for each kind. Its fields seed a draft notebook
  (``seed`` is the section heading; ``""`` seeds body text without a heading).
- ``SUMMARY`` is the one public sentence per kind (listing text, course card,
  portfolio abstract or chapter table summary). It is never seeded.
- ``INTERNAL_NOTES`` is CMS and build-brief only. Next steps are tracked as
  Kanban cards, not as plan fields.

Stored locations are translated by ``plan_patch``; ``parse_plan_file`` reads the
``## <label or key>`` sections of a human-written plan file.
"""
from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from typing import Any

from markdown_it import MarkdownIt


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    prompt: str
    # Draft heading. None: never seeded. "": body text without a heading.
    seed: str | None = None
    # Needed for a useful first draft; reported as missing until written.
    core: bool = False


PLAN: dict[str, tuple[Field, ...]] = {
    "post": (
        Field("content", "Outline", "What will you explain? List the sections and their main points.", seed="", core=True),
        Field("audience", "Audience", "Who will read this, and what should they already know?", seed="Who this is for"),
        Field("evidence", "Examples and evidence", "Which examples, experiments, or sources support the argument?", seed="Examples and evidence"),
        Field("references", "References", "Links and sources to cite.", seed="References"),
    ),
    "portfolio": (
        Field("introduction", "Problem", "What problem does this solve, and why does it matter?", seed="The problem", core=True),
        Field("what_it_contains", "What it contains", "The components, deliverables, and what you will build.", seed="What it contains", core=True),
        Field("intended_users", "Intended users", "Who will use this, and for which tasks?", seed="Who it is for"),
        Field("approach", "Implementation approach", "Main design decisions, tools, and build sequence.", seed="Implementation approach"),
        Field("success_criteria", "Success criteria", "How will you show that it works?", seed="How to evaluate it"),
        Field("references", "References", "Sources, prior work, and related reading.", seed="References"),
    ),
    "course": (
        Field("purpose", "Purpose", "What will learners be able to do, and why does this course exist?", seed="About this course", core=True),
        Field("audience", "Audience and prerequisites", "Who it is for, what they should already know, and which tools or hardware they need.", seed="Who this is for", core=True),
        Field("outcomes", "Learning outcomes", "What will learners be able to do by the end?", seed="Learning outcomes", core=True),
        Field("running_project", "Running project", "Which artifact develops across the chapters?", seed="The running project"),
        Field("assessment", "Practice and assessment", "Which exercises and evidence show understanding?", seed="Practice and assessment"),
        Field("references", "References", "Further reading, datasets, and resources.", seed="References"),
    ),
    "chapter": (
        Field("content", "Outline", "What will this chapter teach? List the explanations, examples, and their order.", seed="", core=True),
        Field("lab_and_evidence", "Practice and evidence", "What will the learner do, and what result shows understanding?", seed="Practice and evidence", core=True),
    ),
}

SUMMARY: dict[str, Field] = {
    "post": Field("summary", "Summary", "One or two sentences for the posts list and page description. State the takeaway."),
    "course": Field("summary", "Card description", "One or two sentences for the courses grid. The purpose below is the longer introduction."),
    "portfolio": Field("summary", "Abstract", "Shown on the portfolio card and entry page. Start draft can fill a first draft from Problem and What it contains. Paste the finished abstract here before publishing; publishing requires it."),
    "chapter": Field("summary", "Course table summary", "One reader-facing sentence for the course table and chapter subtitle."),
}

INTERNAL_NOTES = Field(
    "internal_notes",
    "Internal notes",
    "Research, decisions, open questions, and scope boundaries. Never shown on the site. Track next steps as Kanban cards.",
)

# Personal notebooks have no writing brief. Their saved body still seeds the draft.
BODY_ONLY: dict[str, tuple[Field, ...]] = {
    "personal": (Field("content", "Content", "Body text for the notebook.", seed=""),),
}


def plan_fields(kind: str) -> tuple[Field, ...]:
    return PLAN.get(kind) or BODY_ONLY.get(kind, ())


def core_keys(kind: str) -> set[str]:
    return {field.key for field in plan_fields(kind) if field.core}


def labels(kind: str) -> dict[str, str]:
    """Human labels for every catalog field of a kind, including its public summary."""
    result = {field.key: field.label for field in plan_fields(kind)}
    if kind in SUMMARY:
        result["summary"] = SUMMARY[kind].label
    result["internal_notes"] = INTERNAL_NOTES.label
    return result


def missing_fields(kind: str, plan: Mapping[str, Any]) -> list[str]:
    """Labels of core fields that have no saved text yet."""
    names = labels(kind)
    return [names[field.key] for field in plan_fields(kind) if field.core and not str(plan.get(field.key) or "").strip()]


def seed_sections(kind: str) -> list[tuple[str, str]]:
    """Draft sections in notebook order: (catalog key, heading)."""
    return [(field.key, field.seed) for field in plan_fields(kind) if field.seed is not None]


def _markdown(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value).strip()
    return "" if value is None else str(value).strip()


def filled_fields(kind: str, plan: Mapping[str, Any], exclude: Collection[str] = ()) -> list[tuple[str, str]]:
    """(label, Markdown) for each non-empty catalog field, in writing order; saved keys outside the catalog are ignored."""
    fields = []
    for field in plan_fields(kind):
        if field.key in exclude:
            continue
        text = _markdown(plan.get(field.key))
        if text:
            fields.append((field.label, text))
    return fields


def plan_schema(kind: str) -> list[dict[str, Any]]:
    """Machine-readable field list for agents: where each field lives and whether it seeds."""
    schema = []
    if kind in SUMMARY:
        schema.append({"key": "summary", "label": SUMMARY[kind].label, "prompt": SUMMARY[kind].prompt, "section": "public", "seed": None, "core": False})
    for field in plan_fields(kind):
        schema.append({"key": field.key, "label": field.label, "prompt": field.prompt, "section": "plan", "seed": field.seed, "core": field.core})
    schema.append({"key": "internal_notes", "label": INTERNAL_NOTES.label, "prompt": INTERNAL_NOTES.prompt, "section": "internal", "seed": None, "core": False})
    return schema


def _normal(text: str) -> str:
    return re.sub(r"[\s_-]+", " ", text.strip()).casefold()


def valid_keys(kind: str) -> list[str]:
    return [item["key"] for item in plan_schema(kind)]


def plan_patch(kind: str, values: Mapping[str, Any]) -> dict[str, Any]:
    """Translate canonical keys into the record shape used by ContentService.create/update.

    Only keys present in ``values`` are returned, so partial updates leave other
    fields alone; an empty string clears a field. Raises ValueError for unknown keys.
    """
    if kind not in PLAN:
        raise ValueError(f"{kind} entries do not have planning fields")
    allowed = set(valid_keys(kind))
    unknown = sorted(set(values) - allowed)
    if unknown:
        raise ValueError(f"unknown planning field(s) for {kind}: {', '.join(unknown)}; valid fields: {', '.join(valid_keys(kind))}")
    plan = {key: "" if value is None else str(value) for key, value in values.items() if key in {field.key for field in plan_fields(kind)}}
    patch: dict[str, Any] = {}
    if "internal_notes" in values:
        patch["internal_notes"] = "" if values["internal_notes"] is None else str(values["internal_notes"])
    if "summary" in values:
        summary = "" if values["summary"] is None else str(values["summary"])
        if kind == "portfolio":
            patch["detail"] = {"abstract": summary}
        elif kind == "chapter":
            plan["summary"] = summary
        else:
            patch["description"] = summary
    if kind == "post":
        if plan:
            patch["planned"] = plan
    elif kind == "course":
        contract: dict[str, Any] = {key: plan.pop(key) for key in ("purpose", "audience") if key in plan}
        if plan:
            contract["planned"] = plan
        if contract:
            patch["contract"] = contract
    elif kind == "portfolio":
        if plan:
            patch.setdefault("detail", {})["planned"] = plan
    elif kind == "chapter" and plan:
        patch["plan"] = plan
    return patch


def parse_plan_file(kind: str, text: str) -> dict[str, str]:
    """Read ``## <label or key>`` sections of a plan file into canonical keys.

    Only sections present in the file are returned. Unknown or duplicate headings
    raise ValueError so that a typo never silently drops text.
    """
    if kind not in PLAN:
        raise ValueError(f"{kind} entries do not have planning fields")
    names: dict[str, str] = {}
    for item in plan_schema(kind):
        names.setdefault(_normal(item["label"]), item["key"])
        names.setdefault(_normal(item["key"]), item["key"])
    tokens = MarkdownIt().parse(text)
    if any(token.type == "heading_open" and token.tag == "h1" for token in tokens):
        raise ValueError("plan files use ## section headings; remove the # title line")
    lines = text.splitlines()
    sections: list[tuple[str, str, int, int]] = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2" and token.map:
            heading = tokens[index + 1].content.strip()
            key = names.get(_normal(heading))
            if key is None:
                raise ValueError(f"unknown plan section ## {heading}; valid sections: {', '.join(item['label'] for item in plan_schema(kind))}")
            sections.append((key, heading, token.map[0], token.map[1]))
    first = sections[0][2] if sections else len(lines)
    if "\n".join(lines[:first]).strip():
        raise ValueError("put plan text under a ## section heading")
    result: dict[str, str] = {}
    for position, (key, heading, _start, end) in enumerate(sections):
        if key in result:
            raise ValueError(f"duplicate plan section: ## {heading}")
        stop = sections[position + 1][2] if position + 1 < len(sections) else len(lines)
        result[key] = "\n".join(lines[end:stop]).strip()
    return result
