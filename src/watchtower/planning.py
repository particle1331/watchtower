"""Shared author prompts and readiness rules for saved, unfinished plans."""

from typing import Any

# key, human label, prompt. These fields are shared by creation and editing.
PLAN_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "post": [
        ("content", "Outline / planned content", "What will you explain? Sketch the sections and their main points."),
        ("audience", "Audience", "Who is this for, and what can they already do?"),
        ("takeaway", "Intended takeaway", "What should the reader understand or be able to do afterward?"),
        ("evidence", "Examples and evidence", "Which examples, experiments, or sources will support the argument?"),
    ],
    "portfolio": [
        ("introduction", "Introduction / problem", "What problem does this project solve, and why does it matter?"),
        ("what_it_contains", "What it contains", "Describe the components, deliverables, and what you will build."),
        ("intended_users", "Intended users", "Who will use this, and for which tasks?"),
        ("approach", "Implementation approach", "Describe the main design decisions, tools, and build sequence."),
        ("success_criteria", "Success criteria", "How will you demonstrate that the project works?"),
        ("scope_notes", "Scope notes", "What belongs in this project, and what is outside its scope?"),
    ],
    "course": [
        ("purpose", "Purpose", "What is this course trying to teach or help the learner build?"),
        ("audience", "Audience", "Who is this for, and what do they already know?"),
        ("summary", "Course summary", "Describe the progression from the starting point to the finished outcome."),
        ("prerequisites", "Prerequisites", "Separate assumed knowledge from required tools."),
        ("outcomes", "Learning outcomes", "What will learners be able to do by the end?"),
        ("running_project", "Running project", "What artifact or project develops across the chapters?"),
        ("constraints", "Tools and constraints", "Which tools, datasets, hardware, costs, or limits shape the work?"),
        ("assessment", "Assessment approach", "What exercises and evidence will demonstrate understanding?"),
    ],
    "chapter": [
        ("content", "Planned content", "What will this chapter teach? Outline the explanations and examples."),
        ("lab_and_evidence", "Planned lab and evidence", "What will learners do, and what result will demonstrate understanding?"),
        ("summary", "Short summary", "One or two sentences for the course chapter table."),
    ],
}
for _fields in PLAN_FIELDS.values():
    _fields.extend([
        ("references", "References", "Links, source material, and useful prior work."),
        ("next_steps", "Next steps", "What should you or a collaborator do next? Record open questions here."),
    ])

REQUIRED = {
    "post": ("content",),
    "portfolio": ("introduction", "what_it_contains"),
    "course": ("purpose", "audience", "summary"),
    "chapter": ("content", "lab_and_evidence"),
}


def missing_fields(kind: str, plan: dict[str, Any]) -> list[str]:
    labels = {key: label for key, label, _ in PLAN_FIELDS.get(kind, [])}
    return [labels[key] for key in REQUIRED.get(kind, ()) if not str(plan.get(key) or "").strip()]


def extra_plan_body(kind: str, plan: dict[str, Any], exclude: set[str]) -> str:
    """Include optional and legacy planning facts without duplicating core prose."""
    labels = {key: label for key, label, _ in PLAN_FIELDS.get(kind, [])}
    parts = []
    for key, value in plan.items():
        if key in exclude or value in (None, "", [], {}):
            continue
        text = "\n".join(f"- {item}" for item in value) if isinstance(value, list) else str(value)
        parts.append(f"## {labels.get(key, key.replace('_', ' ').capitalize())}\n\n{text}")
    return "\n\n".join(parts)


def starter_chunks(body: str, limit: int = 20_000) -> list[str]:
    """Preserve every character while preferring Markdown block boundaries."""
    chunks = []
    while len(body) > limit:
        split = body.rfind("\n\n", 0, limit)
        split = split + 2 if split > 0 else limit
        chunks.append(body[:split])
        body = body[split:]
    if body:
        chunks.append(body)
    return chunks
