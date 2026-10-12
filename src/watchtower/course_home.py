"""Structured course-home prose, one-time seeds, and lossless legacy extraction."""
from __future__ import annotations

import re

import nbformat
from markdown_it import MarkdownIt

from watchtower.models import CourseHome
from watchtower.services.workspace import ServiceError

HOME_FIELDS = (
    ("outcome", "Course outcome"),
    ("description", "Course description"),
    ("requirements", "Requirements"),
    ("prerequisites", "Prerequisites"),
    ("references", "References"),
)
HOME_LIST_FIELDS = {"requirements", "prerequisites", "references"}


def seeded_home(plan: dict) -> CourseHome:
    """Plan fields share the home keys, so starting copies each one once."""
    def text(key: str) -> str:
        value = plan.get(key) or ""
        return "\n".join(f"- {item}" for item in value) if isinstance(value, list) else str(value)
    return CourseHome.model_validate({key: text(key) for key, _ in HOME_FIELDS})


def nested_headings(body: str) -> str:
    """Keep authored headings beneath the six fixed home sections, including Setext."""
    lines = body.splitlines()
    tokens = MarkdownIt().parse(body)
    for index, token in reversed(list(enumerate(tokens))):
        if token.type == "heading_open" and token.map and int(token.tag[1:]) < 3:
            start, end = token.map
            title = tokens[index + 1].content
            lines[start:end] = [f"### {title}"]
    return "\n".join(lines)


def legacy_home(notebook: nbformat.NotebookNode, title: str, chapter_names: set[str]) -> CourseHome:
    """Preserve prose; replace only the old title/include and recognizable chapter tables."""
    if any(cell.cell_type != "markdown" or cell.get("attachments") for cell in notebook.cells):
        raise ServiceError("Course-home migration requires Markdown-only cells without embedded attachments; retain executable material in a chapter before migrating.")
    body = "\n\n".join(cell.source for cell in notebook.cells)
    lines = body.splitlines()
    tokens = MarkdownIt("commonmark").enable("table").parse(body)
    ranges = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h1" and token.map and tokens[index + 1].content == title:
            ranges.append(tuple(token.map))
        if token.type == "table_open" and token.map:
            start, end = token.map
            table = "\n".join(lines[start:end])
            targets = re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", table)
            if targets and "chapter" in lines[start].casefold() and all(target.rsplit("/", 1)[-1].rsplit(".", 1)[0] in chapter_names for target in targets):
                if start >= 2 and lines[start - 2].strip().casefold() == "## learning path":
                    start -= 2
                ranges.append((start, end))
    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    body = re.sub(r"\{\{<\s*include\s+_course-context\.md\s*>\}\}", "", "\n".join(lines)).strip()
    explicit_references = ""
    match = re.search(r"(?m)^\*\*Reading sources[.:]?\*\*.*", body)
    if match:
        explicit_references, body = body[match.start():], body[:match.start()].rstrip()
    lines = body.splitlines()
    tokens = MarkdownIt().parse(body)
    sections = [(token.map[0], token.map[1], tokens[index + 1].content.casefold()) for index, token in enumerate(tokens)
                if token.type == "heading_open" and token.tag == "h2" and token.map]
    parts: dict[str, list[str]] = {key: [] for key, _ in HOME_FIELDS}
    if explicit_references:
        parts["references"].append(explicit_references)
    parts["description"].append("\n".join(lines[:sections[0][0] if sections else len(lines)]).strip())
    for index, (start, after, heading) in enumerate(sections):
        end = sections[index + 1][0] if index + 1 < len(sections) else len(lines)
        content = "\n".join(lines[after:end]).strip()
        if heading in {"outcome", "expected outcome", "what you will finish with", "learning outcomes", "what you'll learn"}:
            parts["outcome"].append(content)
        elif heading in {"prerequisites", "who this is for"}:
            current = "prerequisites"
            for paragraph in re.split(r"\n\s*\n", content):
                if re.match(r"\*\*(?:tools|tooling|hardware|access)[.:]?\*\*", paragraph, re.I) or re.match(r"###\s*(?:tools?|tooling|hardware|access|requirements)\b", paragraph, re.I):
                    current = "requirements"
                    if paragraph.startswith("**"):
                        paragraph = re.sub(r"^\*\*(?:tools|tooling|hardware|access)[.:]?\*\*\s*", "", paragraph, flags=re.I)
                    else:
                        continue
                elif re.match(r"\*\*knowledge[.:]?\*\*|###\s*(?:knowledge|prerequisites)\b", paragraph, re.I):
                    current = "prerequisites"
                    if paragraph.startswith("**"):
                        paragraph = re.sub(r"^\*\*knowledge[.:]?\*\*\s*", "", paragraph, flags=re.I)
                    else:
                        continue
                elif re.match(r"### ", paragraph, re.I):
                    current = "prerequisites"
                if paragraph.strip():
                    parts[current].append(paragraph)
        elif heading in {"references", "sources", "reading sources"}:
            parts["references"].append(content)
        elif heading == "execution at a glance":
            parts["requirements"].append(content)
        elif heading in {"about this course", "course description"}:
            parts["description"].append(content)
        else:
            parts["description"].append("\n".join(lines[start:end]).strip())
    if not parts["outcome"]:
        for index, paragraph in enumerate(parts["description"]):
            blocks = re.split(r"\n\s*\n", paragraph)
            outcome = [block for block in blocks if block.startswith("By the end,")]
            if outcome:
                parts["outcome"].extend(outcome)
                parts["description"][index] = "\n\n".join(block for block in blocks if block not in outcome)
    if not parts["references"]:
        links = {}
        for token in MarkdownIt().parse(body):
            children = token.children or []
            for index, child in enumerate(children):
                if child.type == "link_open" and (href := str(child.attrGet("href") or "")).startswith(("https://", "http://")):
                    label = ""
                    for text in children[index + 1:]:
                        if text.type == "link_close":
                            break
                        label += text.content
                    links.setdefault(href, label)
        parts["references"].extend(f"- [{label}]({href})" for href, label in links.items())
    return CourseHome.model_validate({key: "\n\n".join(part for part in values if part) for key, values in parts.items()})
