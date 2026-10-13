"""Authoring fields shared by the CMS, CLI, draft seeding and the build brief.

Every planning field is defined once here:

- ``PLAN`` is the writing brief for each kind. Its fields seed a draft notebook
  (``seed`` is the section heading; ``""`` seeds body text without a heading).
- ``SUMMARY`` is the one public sentence per kind (listing text, course card,
  portfolio abstract or chapter table summary). It is never seeded.
- ``INTERNAL_NOTES`` keeps the content entity's unfinished context and to-dos
  together. Linked Kanban cards carry context for individual executions.

Post, portfolio and chapter fields are temporary starter inputs. They are saved
only while Planned, then consumed into notebook cells and removed from metadata.
Their labels and keys describe the authoring form, not permanent domain fields.

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
    # Earlier labels still accepted in plan files; the label above is the draft heading.
    aliases: tuple[str, ...] = ()


PLAN: dict[str, tuple[Field, ...]] = {
    # Labels equal the draft headings (seed), so the plan and the started draft show one form.
    # The draft is definitive: change a heading there and here together. Body-only fields
    # (seed "") have no heading in the draft, so their label names the form field only.
    "post": (
        Field("introduction", "The problem", "What question or problem will this post address, and why does it matter?", seed="The problem", core=True, aliases=("Problem",)),
        Field("content", "Planned content", "What will you explain? Describe the intended readers, sections, examples, and their main points.", seed="Planned content", core=True, aliases=("Outline",)),
        Field("evidence", "Planned evidence", "Which examples, experiments, results, or sources will support the post?", seed="Planned evidence", core=True, aliases=("Examples and evidence",)),
    ),
    "portfolio": (
        Field("introduction", "The problem", "What problem does this solve, and why does it matter?", seed="The problem", core=True, aliases=("Problem",)),
        Field("content", "Planned content", "What will the project page contain? Describe the components, intended users, deliverables, and implementation approach.", seed="Planned content", core=True, aliases=("What it contains", "what_it_contains")),
        Field("evidence", "Planned evidence", "Which tests, results, demonstrations, or sources will show that the project works?", seed="Planned evidence", core=True, aliases=("How to evaluate it", "Success criteria", "success_criteria")),
    ),
    # Same fields, labels and prompts as the started course home (course_home.HOME_FIELDS),
    # so the plan and the draft show one form. Starting copies them into contract.home.
    "course": (
        Field("outcome", "Course outcome", "Describe the project, skill, or framework the learner will finish with or master. Markdown is supported.", core=True),
        Field("description", "Course description", "Explain the purpose, intended audience, scope, and what to expect. Keep internal design rules and execution notes in Internal notes. Markdown is supported.", core=True),
        Field("requirements", "Requirements", "One requirement per line, such as hardware, software, account, data, or access needed to participate. Markdown is supported."),
        Field("prerequisites", "Prerequisites", "One assumed skill or knowledge prerequisite per line. Markdown is supported.", core=True),
        Field("references", "References", "One outside reference per line. Markdown links are supported."),
    ),
    "chapter": (
        Field("introduction", "The problem", "What question or problem will this chapter address, and why does it matter to the learner?", seed="The problem", core=True, aliases=("Problem",)),
        Field("content", "Planned content", "What will this chapter teach? Describe the explanations, examples, and their order.", seed="Planned content", core=True, aliases=("Outline",)),
        Field("lab_and_evidence", "Planned evidence", "What will the learner do, and which examples, experiments, results, or sources will show understanding?", seed="Planned evidence", core=True, aliases=("Practice and evidence", "evidence")),
    ),
}

SUMMARY: dict[str, Field] = {
    "post": Field("summary", "Summary", "One or two sentences for the Posts listing. State the takeaway. Kept outside the full post notebook page."),
    "course": Field("summary", "Card description", "One or two sentences for the courses grid. The course home has the longer description."),
    "portfolio": Field("summary", "Abstract", "Shown on the portfolio listing. Start draft can fill a first draft from The problem and Planned content. Paste the finished abstract here before publishing; publishing requires it."),
    "chapter": Field("summary", "Course table summary", "One reader-facing sentence for the course table. Kept outside the full chapter notebook page."),
}

INTERNAL_NOTES = Field(
    "internal_notes",
    "Internal notes",
    "Markdown notes for research, decisions and open questions. The entity's separate internal_todos checklist tracks unfinished work. Linked Kanban cards execute scoped work and hold temporary task context. Never shown on the site.",
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


def portfolio_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Read older briefs through the three-section form, preserving their saved keys.

    Explicit content/evidence values, including blanks, take precedence. Legacy
    supporting material stays inside those sections until the author revises it.
    """
    result = dict(plan)
    for key, opening, supporting in (
        ("content", "what_it_contains", (("intended_users", "Who it is for"), ("approach", "Implementation approach"))),
        ("evidence", "success_criteria", (("references", "References"),)),
    ):
        if key in result:
            continue
        parts = [_markdown(plan.get(opening))]
        for legacy, heading in supporting:
            body = _markdown(plan.get(legacy))
            if legacy == "references" and body and "\n\n" not in body and not re.search(r"(?m)^\s{0,3}(?:[-*+] |\d+[.)] |#{1,6} |>|\|)", body):
                body = "\n".join(f"- {line.strip()}" for line in body.splitlines() if line.strip())
            if body:
                parts.append(f"### {heading}\n\n{body}")
        result[key] = "\n\n".join(part for part in parts if part)
    return result


def post_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Fold older audience/reference fields into the three-section post brief.

    Saved legacy keys remain intact. The new introduction key marks an already
    normalized brief, so later edits and explicit blanks never re-add old text.
    """
    result = dict(plan)
    if "introduction" in result:
        return result
    for key, legacy, heading in (("content", "audience", "Who this is for"), ("evidence", "references", "References")):
        body = _markdown(plan.get(legacy))
        if not body:
            continue
        if legacy == "references" and "\n\n" not in body and not re.search(r"(?m)^\s{0,3}(?:[-*+] |\d+[.)] |#{1,6} |>|\|)", body):
            body = "\n".join(f"- {line.strip()}" for line in body.splitlines() if line.strip())
        result[key] = "\n\n".join(part for part in (_markdown(plan.get(key)), f"### {heading}\n\n{body}") if part)
        result["introduction"] = ""
    return result


def filled_fields(kind: str, plan: Mapping[str, Any], exclude: Collection[str] = ()) -> list[tuple[str, str]]:
    """(label, Markdown) for each non-empty catalog field, in writing order; saved keys outside the catalog are ignored."""
    if kind == "portfolio":
        plan = portfolio_plan(plan)
    elif kind == "post":
        plan = post_plan(plan)
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
    elif kind == "course" and plan:
        patch["contract"] = {"planned": plan}
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
    for field in plan_fields(kind):
        for alias in field.aliases:
            names.setdefault(_normal(alias), field.key)
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
