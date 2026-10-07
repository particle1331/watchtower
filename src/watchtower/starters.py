"""One-time draft sections drawn from explicitly supported planning fields."""
from typing import Any

from markdown_it import MarkdownIt

from watchtower.services.workspace import ServiceError

SECTIONS = {
    "post": [("audience", "Who this is for"), ("takeaway", "What you will learn"),
             ("content", ""), ("evidence", "Examples and evidence"), ("references", "References")],
    "portfolio": [("introduction", "The problem"), ("intended_users", "Who it is for"),
                  ("what_it_contains", "What it contains"), ("approach", "Implementation approach"),
                  ("success_criteria", "How to evaluate it")],
    "course": [("purpose", "About this course"), ("audience", "Who this is for"),
               ("summary", "Course progression"), ("prerequisites", "Prerequisites"),
               ("outcomes", "Learning outcomes"), ("running_project", "The running project"),
               ("constraints", "Tools and requirements"), ("assessment", "Practice and assessment"),
               ("references", "References")],
    "chapter": [("content", ""), ("lab_and_evidence", "Practice and evidence"),
                ("references", "References")],
    "personal": [("content", "")],
}


def portfolio_abstract(plan: dict[str, Any]) -> str:
    """Seed a short, editable abstract from the opening prose, without inventing claims."""
    paragraphs = []
    for key in ("introduction", "what_it_contains"):
        tokens = MarkdownIt().parse(str(plan.get(key) or ""))
        for index, token in enumerate(tokens):
            if token.type != "inline" or index == 0 or tokens[index - 1].type != "paragraph_open":
                continue
            text = "".join(" " if child.type in {"softbreak", "hardbreak"} else child.content
                           for child in token.children or [] if child.type in {"text", "code_inline", "softbreak", "hardbreak"})
            text = " ".join(text.split())
            if text:
                if text not in paragraphs:
                    paragraphs.append(text)
                break
    text = " ".join(paragraphs)
    words = text.split()
    return " ".join(words[:80]).rstrip(".,;:") + "…" if len(words) > 80 else text


def draft_sections(kind: str, plan: dict[str, Any]) -> list[str]:
    """Preserve Markdown and fences; keep notes and unknown plan fields internal."""
    sections = []
    for key, heading in SECTIONS.get(kind, []):
        value = plan.get(key)
        if not value:
            continue
        body = "\n".join(f"- {item}" for item in value) if isinstance(value, list) else str(value)
        if not body.strip():
            continue
        lines = body.strip().splitlines()
        # The notebook title owns the only H1, including with Setext plan headings.
        for token in reversed(MarkdownIt().parse(body.strip())):
            if token.type == "heading_open" and token.tag == "h1" and token.map:
                start, end = token.map
                if lines[start].lstrip().startswith("#"):
                    indent = len(lines[start]) - len(lines[start].lstrip())
                    lines[start] = lines[start][:indent] + "#" + lines[start][indent:]
                else:
                    lines[end - 1] = "---"
        body = "\n".join(lines)
        section = f"## {heading}\n\n{body}" if heading else body
        lines = section.splitlines(keepends=True)
        boundaries = sorted({0, len(lines), *(token.map[0] for token in MarkdownIt().parse(section) if token.level == 0 and token.map)})
        chunk = ""
        for start, end in zip(boundaries, boundaries[1:], strict=False):
            block = "".join(lines[start:end])
            if len(block) > 20_000:
                raise ServiceError(f"Plan field {key} contains a Markdown block over 20,000 characters; split it before starting.")
            if len(chunk) + len(block) > 20_000:
                sections.append(chunk)
                chunk = ""
            chunk += block
        if chunk:
            sections.append(chunk)
    return sections
