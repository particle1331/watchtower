"""Catalog and course context for active knowledge work."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML

CATALOG_PATH = Path("knowledge/catalog.yaml")
SIDEBAR_PATH = Path("knowledge/sidebar.yaml")
ARCHIVE_PATH = Path("archive/2026-09-30")
KINDS = {"post", "course", "chapter", "portfolio", "project"}
VISIBILITIES = {"public", "private"}
LIFECYCLES = {"planned", "draft", "published"}
ACTIVE_ROOTS = {
    "post": Path("nb/posts"), "course": Path("nb/courses"),
    "chapter": Path("nb/courses"), "portfolio": Path("nb/portfolio"),
    "project": Path("projects"),
}
INCLUDE_NAME = "_course-context.md"
INCLUDE_MARKER = "{{< include _course-context.md >}}"


def load_catalog() -> list[dict[str, Any]]:
    if not CATALOG_PATH.exists():
        raise FileNotFoundError(f"catalog missing: {CATALOG_PATH}")
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("artifacts"), list):
        raise ValueError(f"{CATALOG_PATH}: expected version: 1 and artifacts: list")
    return data["artifacts"]


def save_catalog(artifacts: list[dict[str, Any]]) -> None:
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(
        yaml.safe_dump({"version": 1, "artifacts": artifacts}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def add_artifact(
    artifact_id: str,
    kind: str,
    path: Path,
    title: str,
    *,
    parent: str | None = None,
    visibility: str = "public",
    lifecycle: str = "draft",
) -> None:
    if kind not in KINDS or visibility not in VISIBILITIES or lifecycle not in LIFECYCLES:
        raise ValueError("invalid artifact kind, visibility, or lifecycle")
    if not path.exists() or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"artifact path must be an existing relative path: {path}")
    if not path.is_relative_to(ACTIVE_ROOTS[kind]):
        raise ValueError(f"{kind} path must be under {ACTIVE_ROOTS[kind]}")
    artifacts = load_catalog()
    if any(a.get("id") == artifact_id or a.get("path") == path.as_posix() for a in artifacts):
        raise ValueError(f"artifact already registered: {artifact_id} or {path}")
    item: dict[str, Any] = {
        "id": artifact_id,
        "kind": kind,
        "title": title,
        "path": path.as_posix(),
        "visibility": visibility,
        "lifecycle": lifecycle,
        "relations": [],
    }
    if parent is not None:
        if not any(a.get("id") == parent and a.get("kind") == "course" for a in artifacts):
            raise ValueError(f"course parent is not registered: {parent}")
        item["parent"] = parent
    artifacts.append(item)
    save_catalog(artifacts)


def get_artifact(name: str) -> dict[str, Any] | None:
    for item in load_catalog():
        if name in {item.get("id"), item.get("path")}:
            return item
        path = item.get("path")
        if item.get("kind") == "course" and name == str(Path(str(path)) / "index.ipynb"):
            return item
        if isinstance(path, str) and Path(name).suffix == "" and name == str(Path(path).with_suffix("")):
            return item
    return None


def load_sidebar_source() -> Any:
    """Load the authored sidebar, initializing it from Quarto on first use."""
    parser = YAML(typ="rt")
    parser.preserve_quotes = True
    if not SIDEBAR_PATH.exists():
        with Path("_quarto.yml").open(encoding="utf-8") as handle:
            config = parser.load(handle)
        SIDEBAR_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SIDEBAR_PATH.open("w", encoding="utf-8") as handle:
            parser.dump({"website": {"sidebar": config.get("website", {}).get("sidebar", [])}}, handle)
    with SIDEBAR_PATH.open(encoding="utf-8") as handle:
        return parser.load(handle)


def publish_artifact(name: str) -> dict[str, Any]:
    """Publish one public course or chapter and synchronize the site."""
    parser = YAML(typ="rt")
    parser.preserve_quotes = True
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        catalog = parser.load(handle)

    artifacts = catalog["artifacts"]
    resolved = get_artifact(name)
    artifact = next(
        (item for item in artifacts if resolved and item.get("id") == resolved.get("id")),
        None,
    )
    if artifact is None:
        raise ValueError(f"no active artifact named '{name}'")
    if artifact.get("kind") not in {"course", "chapter"}:
        raise ValueError("publish accepts a course or chapter artifact")
    if artifact.get("visibility") != "public":
        raise ValueError(f"{artifact['id']} is private; set visibility to public first")
    if artifact.get("kind") == "chapter":
        parent = next(
            (item for item in artifacts if item.get("id") == artifact.get("parent")),
            None,
        )
        if parent is None or parent.get("kind") != "course":
            raise ValueError(f"{artifact['id']} has no registered course parent")
        if parent.get("lifecycle") != "published" or parent.get("visibility") != "public":
            raise ValueError(f"publish the public parent course before {artifact['id']}")

    artifact["lifecycle"] = "published"
    with CATALOG_PATH.open("w", encoding="utf-8") as handle:
        parser.dump(catalog, handle)
    sync_site()
    return dict(artifact)


def _sync_published_course_sidebars(
    config: dict[str, Any],
    artifacts: list[dict[str, Any]],
    published: dict[str, dict[str, Any]],
) -> None:
    """Hide unpublished chapters from navigation for published courses."""
    courses_by_slug = {
        Path(str(course["path"])).name: course
        for course in artifacts
        if course.get("kind") == "course"
    }
    sidebar = config.get("website", {}).get("sidebar", [])
    if not isinstance(sidebar, list):
        return

    def chapter_path(node: Any, chapter_paths: set[str]) -> str | None:
        if isinstance(node, list):
            for child in node:
                found = chapter_path(child, chapter_paths)
                if found is not None:
                    return found
        if isinstance(node, dict):
            href = node.get("href")
            if isinstance(href, str) and href in chapter_paths:
                return href
            for child in node.get("contents", []):
                found = chapter_path(child, chapter_paths)
                if found is not None:
                    return found
        return None

    def filter_node(node: Any, chapter_paths: set[str], visible_paths: set[str], *, root: bool = False) -> Any | None:
        if not isinstance(node, dict):
            return node

        contents = node.get("contents")
        if isinstance(contents, list):
            node["contents"] = [
                kept for child in contents
                if (kept := filter_node(child, chapter_paths, visible_paths)) is not None
            ]

        href = node.get("href")
        if isinstance(href, str) and href in chapter_paths and href not in visible_paths:
            replacement = chapter_path(node.get("contents", []), visible_paths)
            if replacement is not None:
                node["href"] = replacement
            elif not root:
                return None

        if node.get("section") and not node.get("contents") and not root:
            href = node.get("href")
            if not isinstance(href, str) or href not in visible_paths:
                return None
        return node

    for entry in sidebar:
        if not isinstance(entry, dict):
            continue
        course = courses_by_slug.get(str(entry.get("id", "")))
        if course is None or course["id"] not in published:
            continue
        children = [item for item in artifacts if item.get("kind") == "chapter" and item.get("parent") == course["id"]]
        chapter_paths = {str(item["path"]) for item in children}
        visible_paths = {
            str(item["path"]) for item in children
            if item.get("visibility") == "public" and item.get("lifecycle") == "published"
        }
        filter_node(entry, chapter_paths, visible_paths, root=True)


def course_file(course: dict[str, Any]) -> Path:
    return Path(str(course["path"])) / "course.yaml"


def load_course(course: dict[str, Any]) -> dict[str, Any]:
    path = course_file(course)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a mapping")
    return data


def course_include(data: dict[str, Any]) -> str:
    planned = data.get("planned", {})
    actualized = data.get("actualized", {})
    if not isinstance(planned, dict) or not isinstance(actualized, dict):
        raise ValueError("course planned and actualized must be mappings")
    purpose = str(data.get("purpose", "")).strip()
    audience = str(data.get("audience", "")).strip()
    plan = str(planned.get("summary", "")).strip()
    actual = str(actualized.get("summary", "")).strip()
    return (
        "## Course at a glance\n\n"
        f"**Purpose:** {purpose}\n\n"
        f"**For:** {audience}\n\n"
        "### Planned path\n\n"
        f"{plan or 'To be planned.'}\n\n"
        "### Actualized work\n\n"
        f"{actual or 'No completed work recorded yet.'}\n"
    )


def render_course_includes() -> list[Path]:
    written: list[Path] = []
    for artifact in load_catalog():
        if artifact.get("kind") != "course":
            continue
        target = Path(str(artifact["path"])) / INCLUDE_NAME
        target.write_text(course_include(load_course(artifact)), encoding="utf-8")
        written.append(target)
    return written


def course_listing(courses: list[dict[str, Any]]) -> str:
    contents = [
        f'    - "{Path(str(course["path"])) / "index.ipynb"}"'
        for course in courses
    ]
    return "\n".join([
        "---",
        'title: "Courses"',
        "page-layout: full",
        "sidebar: false",
        "toc: false",
        "listing:",
        "  contents:",
        *contents,
        "  type: grid",
        "  sort: false",
        "  fields:",
        "    - title",
        "    - description",
        "    - image",
        "---",
        "",
        "Course syllabi and notes.",
        "",
    ])


def sync_site() -> None:
    """Render only public, published knowledge pages in the Quarto site."""
    path = Path("_quarto.yml")
    parser = YAML(typ="rt")
    parser.preserve_quotes = True
    with path.open(encoding="utf-8") as handle:
        config = parser.load(handle)
    sidebar_source = load_sidebar_source()
    config.setdefault("website", {})["sidebar"] = sidebar_source.get("website", {}).get("sidebar", [])
    artifacts = load_catalog()
    published = {
        str(a["id"]): a for a in artifacts
        if a.get("visibility") == "public" and a.get("lifecycle") == "published"
    }
    render = ["index.qmd", "resume.qmd", "nb/photos/photos.ipynb"]
    navbar = [
        {"href": "resume.qmd", "text": "résumé"},
        {"href": "nb/photos/photos.ipynb", "text": "personal"},
    ]
    posts = [a for a in published.values() if a.get("kind") == "post"]
    if posts:
        render.append("posts.qmd")
        render.extend(str(a["path"]) for a in posts)
        navbar.append({"href": "posts.qmd", "text": "posts"})
    courses = [a for a in published.values() if a.get("kind") == "course"]
    if courses:
        Path("courses.qmd").write_text(course_listing(courses), encoding="utf-8")
        render.append("courses.qmd")
        navbar.append({"href": "courses.qmd", "text": "courses"})
    for item in published.values():
        kind = item.get("kind")
        if kind == "course":
            home = str(Path(str(item["path"])) / "index.ipynb")
            render.append(home)
        elif kind == "chapter" and item.get("parent") in published:
            render.append(str(item["path"]))
        elif kind == "portfolio":
            render.append(str(item["path"]))
            navbar.append({"href": str(item["path"]), "text": str(item["title"])})
    render.append("!archive/**")
    config.setdefault("project", {})["render"] = render
    config.setdefault("website", {}).setdefault("navbar", {})["left"] = navbar
    _sync_published_course_sidebars(config, artifacts, published)
    with path.open("w", encoding="utf-8") as handle:
        parser.dump(config, handle)


def context(name: str) -> dict[str, Any]:
    artifact = get_artifact(name)
    if artifact is None:
        raise FileNotFoundError(f"no active artifact named '{name}'")
    target = str(Path(str(artifact["path"])) / "index.ipynb") if artifact["kind"] == "course" else artifact["path"]
    result: dict[str, Any] = {"artifact": artifact, "reading_paths": {"target": target}}
    course = artifact if artifact["kind"] == "course" else get_artifact(str(artifact.get("parent", "")))
    if course is not None and course.get("kind") == "course":
        folder = Path(str(course["path"]))
        result["course"] = load_course(course)
        result["reading_paths"] = {"course_home": str(folder / "index.ipynb")}
        overview = next(
            (a for a in load_catalog() if a.get("parent") == course["id"] and Path(str(a.get("path"))).stem.endswith("overview")),
            None,
        )
        if overview is not None:
            result["reading_paths"]["overview"] = overview["path"]
        result["reading_paths"]["target"] = target
    return result


def context_json(name: str) -> str:
    return json.dumps(context(name), indent=2, ensure_ascii=False)


def validate() -> list[str]:
    errors: list[str] = []
    artifacts = load_catalog()
    ids: set[str] = set()
    paths: set[str] = set()
    for item in artifacts:
        if not isinstance(item, dict):
            errors.append("artifact must be a mapping")
            continue
        artifact_id, kind, path = item.get("id"), item.get("kind"), item.get("path")
        if not isinstance(artifact_id, str) or not artifact_id:
            errors.append("artifact has no id")
            continue
        if artifact_id in ids:
            errors.append(f"duplicate id: {artifact_id}")
        ids.add(artifact_id)
        if kind not in KINDS:
            errors.append(f"{artifact_id}: invalid kind {kind}")
        if not isinstance(path, str) or not path or Path(path).is_absolute() or ".." in Path(path).parts:
            errors.append(f"{artifact_id}: invalid path")
            continue
        if path in paths:
            errors.append(f"duplicate path: {path}")
        paths.add(path)
        if not Path(path).exists():
            errors.append(f"{artifact_id}: missing path {path}")
        if kind in ACTIVE_ROOTS and not Path(path).is_relative_to(ACTIVE_ROOTS[kind]):
            errors.append(f"{artifact_id}: {kind} path must be under {ACTIVE_ROOTS[kind]}")
        if item.get("visibility") not in VISIBILITIES:
            errors.append(f"{artifact_id}: invalid visibility")
        if item.get("lifecycle") not in LIFECYCLES:
            errors.append(f"{artifact_id}: invalid lifecycle")
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            errors.append(f"{artifact_id}: title is required")
        if not isinstance(item.get("relations"), list):
            errors.append(f"{artifact_id}: relations must be a list")
    for item in artifacts:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        artifact_id = item["id"]
        parent = item.get("parent")
        if item.get("kind") == "chapter" and not any(a.get("id") == parent and a.get("kind") == "course" for a in artifacts):
            errors.append(f"{artifact_id}: missing course parent {parent}")
        for relation in item.get("relations", []) if isinstance(item.get("relations"), list) else []:
            if relation not in ids:
                errors.append(f"{artifact_id}: unknown relation {relation}")
        if item.get("kind") == "course":
            folder = Path(str(item.get("path")))
            course_yaml = folder / "course.yaml"
            home = folder / "index.ipynb"
            if not course_yaml.exists():
                errors.append(f"{artifact_id}: missing {course_yaml}")
            else:
                try:
                    data = load_course(item)
                    if data.get("id") != artifact_id:
                        errors.append(f"{artifact_id}: course YAML id differs")
                    if not isinstance(data.get("planned"), dict) or not isinstance(data.get("actualized"), dict):
                        errors.append(f"{artifact_id}: planned and actualized sections required")
                    elif any(not isinstance(data[part].get("summary"), str) for part in ("planned", "actualized")):
                        errors.append(f"{artifact_id}: planned and actualized summaries must be strings")
                    if any(not isinstance(data.get(field), str) for field in ("purpose", "audience")):
                        errors.append(f"{artifact_id}: purpose and audience must be strings")
                    include = folder / INCLUDE_NAME
                    if include.exists() and include.read_text(encoding="utf-8") != course_include(data):
                        errors.append(f"{artifact_id}: generated course include is stale")
                except (ValueError, yaml.YAMLError) as error:
                    errors.append(f"{artifact_id}: {error}")
            if not home.exists():
                errors.append(f"{artifact_id}: missing {home}")
            else:
                from .notebook import read_notebook

                source = "\n".join(str(c.get("source", "")) for c in read_notebook(home)["cells"])
                if INCLUDE_MARKER not in source:
                    errors.append(f"{artifact_id}: home missing include marker")
        if item.get("kind") == "chapter" and item.get("lifecycle") == "published":
            course = next((a for a in artifacts if a.get("id") == parent), None)
            if course is None or course.get("lifecycle") != "published":
                errors.append(f"{artifact_id}: published chapter needs a published parent course")
    active_files = (
        list(Path("nb/posts").glob("*.ipynb"))
        + list(Path("nb/courses").glob("*/*.ipynb"))
        + list(Path("nb/portfolio").glob("*.qmd"))
        + list(Path("nb/portfolio").glob("*.ipynb"))
        + ([p for p in Path("projects").iterdir() if p.is_dir() and (p / "pyproject.toml").exists()] if Path("projects").exists() else [])
    )
    for path in active_files:
        if path.name == "index.ipynb" and path.parent.as_posix() in paths:
            continue
        if path.as_posix() not in paths:
            errors.append(f"unregistered active path: {path}")
    return errors
