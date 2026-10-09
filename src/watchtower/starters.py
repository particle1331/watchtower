"""One-time draft sections drawn from explicitly supported planning fields."""
import hashlib
import re
from typing import Any

from markdown_it import MarkdownIt

from watchtower.planning import BODY_ONLY, PLAN, seed_sections
from watchtower.services.workspace import ServiceError

# Each kind seeds its writing-brief fields in order. An empty heading seeds body text.
SECTIONS: dict[str, list[tuple[str, str]]] = {kind: seed_sections(kind) for kind in (*PLAN, *BODY_ONLY)}


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


def draft_notebook_cells(kind: str, title: str, plan: dict[str, Any]) -> list[str]:
    """Notebook bodies for a fresh draft: the title and the seeded plan sections."""
    return [f"# {title}\n", *draft_sections(kind, plan)]


def seed_fingerprint(bodies: list[str]) -> str:
    """Identity of a draft's seeded sections, excluding the title cell.

    A notebook matching its fingerprint is still exactly its last seed: plan
    saves may refresh it, and no hand edit can be lost. A single hand edit
    changes the fingerprint and freezes the draft.
    """
    return hashlib.sha256("\x1e".join(bodies[1:]).encode()).hexdigest()


def draft_sections(kind: str, plan: dict[str, Any]) -> list[str]:
    """Preserve Markdown and fences; keep notes and unknown plan fields internal."""
    sections = []
    for key, heading in SECTIONS.get(kind, []):
        value = plan.get(key)
        if not value:
            continue
        if isinstance(value, list):
            body = "\n".join(f"- {item}" for item in value)
        else:
            body = str(value)
            if key == "references":
                # Plain reference lines are a list of items, not one soft-wrapped paragraph.
                items = [line.strip() for line in body.strip().splitlines() if line.strip()]
                already_markdown = "\n\n" in body.strip() or re.search(r"(?m)^\s{0,3}(?:[-*+] |\d+[.)] |#{1,6} |>|\|)", body)
                if len(items) > 1 and not already_markdown:
                    body = "\n".join(f"- {item}" for item in items)
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
