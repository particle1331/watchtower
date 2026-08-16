"""Notebook cell operations for agents: read and edit cells in `.ipynb` files.

These wrappers expose notebook contents as plain text to AI agents without
the JSON noise of the raw `.ipynb` format. Writes use nbformat to preserve
outputs and metadata when mutating a single cell.

Cell locators (--index / --tag / --label):
  --index N    0-based positional index (fragile under reordering)
  --tag foo    matches a cell whose Jupyter tags include `foo`
  --label foo  matches a cell whose first nonblank line is `#| label: foo`

Commands that *write* (including `tag`) require a unique match; `cat` and
`remove-cell` may match multiple cells and act on all of them.
"""


import difflib
import subprocess
from pathlib import Path

import nbformat

from . import obfuscate
from .inspect import resolve_ipynb

CELL_TYPE_MD = "markdown"
CELL_TYPE_CODE = "code"

# Hard limit on cell source length for writes (agents should not create
# massive cells). Raise ValueError if exceeded.
MAX_CELL_SOURCE_CHARS = 20_000

# Default per-cell source limit for `wt cat` reads (protects agent context
# windows). Pass --limit 0 to disable (show full source).
DEFAULT_READ_LIMIT = 4096


# ---Short alias -> nbformat cell_type value -------------------------------
_TYPE_ALIASES = {
    "md": CELL_TYPE_MD,
    "markdown": CELL_TYPE_MD,
    "code": CELL_TYPE_CODE,
}


def _normalize_cell_type(cell_type: str) -> str:
    key = cell_type.strip().lower()
    if key not in _TYPE_ALIASES:
        raise ValueError(
            f"unknown cell type '{cell_type}'. use 'md' or 'code'."
        )
    return _TYPE_ALIASES[key]


def read_notebook(path: Path) -> nbformat.NotebookNode:
    return nbformat.read(path, as_version=nbformat.NO_CONVERT)


def check_source_limit(source: str) -> None:
    """Guard against excessively long cell sources from agents."""
    if len(source) > MAX_CELL_SOURCE_CHARS:
        raise ValueError(
            f"cell source too long: {len(source)} chars "
            f"(limit {MAX_CELL_SOURCE_CHARS}). "
            "Break into smaller cells or trim the content."
        )


def cell_tags(cell: nbformat.NotebookNode) -> list[str]:
    return list(cell.get("metadata", {}).get("tags", []))


def _cell_label(cell: nbformat.NotebookNode) -> str | None:
    """Quarto cell label from a `#| label: <x>` pragma in the options header.

    The options header is the leading run of `#|` lines at the top of the
    source; a label on any of them counts.
    """
    for line in cell.get("source", "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#|"):
            return None
        if "label:" in stripped:
            parts = stripped.split("label:", 1)
            if len(parts) == 2:
                return parts[1].strip()
    return None


def _render_cell(
    cell: nbformat.NotebookNode,
    index: int,
    *,
    offset: int = 0,
    limit: int | None = None,
    with_outputs: bool = False,
    out_offset: int = 0,
    out_limit: int | None = None,
    context: bool = False,
    decode_solutions: bool = False,
) -> str:
    """Render one cell as plain markdown with a header marker.

    --offset/--limit slice the cell *source* (char-wise).
    --with-outputs appends the cell's outputs, each with its own header.
    --out-offset/--out-limit slice *each output's* text body (char-wise).
    When sliced, headers carry the range and total so an agent can chain
    reads without re-paying for bytes already seen.

    `context` marks the header of cells shown only as surrounding context
    for a `--context` read. `decode_solutions` replaces the stored source
    of solution-tagged cells with its decoded plaintext (spoiler opt-in).
    """
    kind = cell["cell_type"]
    extras: list[str] = []
    tags = cell_tags(cell)
    if tags:
        extras.append(f"tags:{','.join(tags)}")
    label = _cell_label(cell)
    if label:
        extras.append(f"label:{label}")
    if context:
        extras.append("context")
    header = f"> cell {index} [{kind}]"
    if extras:
        header += " " + " ".join(extras)
    body = cell.get("source", "")
    decoded_solution = decode_solutions and "solution" in tags
    if decoded_solution:
        body = obfuscate.deobfuscate(obfuscate.unwrap(body))
    total = len(body)
    if limit is not None:
        body = body[offset:offset + limit]
        shown = len(body)
        if shown < total or offset:
            header += f" src[{offset}:{offset + shown}] of {total}"
    elif offset:
        body = body[offset:]
        shown = len(body)
        header += f" src[{offset}:{offset + shown}] of {total}"
    out: list[str] = []
    if kind == "code" and not decoded_solution:
        fence = "```{python}\n"
        out.append(f"{header}\n\n{fence}{body}\n```" if body else f"{header}\n\n{fence}\n```")
    else:
        out.append(f"{header}\n\n{body}" if body else header)
    if with_outputs and kind == "code":
        outputs = cell.get("outputs", []) or []
        out.append(f"> cell {index} outputs ({len(outputs)} total)")
        for k, o in enumerate(outputs):
            out.append(_render_output(o, k, index, out_offset, out_limit))
    return "\n\n".join(out)


def _render_output(
    output: nbformat.NotebookNode,
    k: int,
    cell_index: int,
    offset: int,
    limit: int | None,
) -> str:
    """Render one cell output with sliceable text body."""
    label, raw = _output_body(output)
    header = f">> cell {cell_index} output {k} [{label}]"
    total = len(raw)
    if limit is not None:
        body = raw[offset:offset + limit]
        shown = len(body)
        if shown < total or offset:
            header += f" out[{offset}:{offset + shown}] of {total}"
    elif offset:
        body = raw[offset:]
        shown = len(body)
        header += f" out[{offset}:{offset + shown}] of {total}"
    else:
        body = raw
    if not body:
        return header
    return f"{header}\n\n```\n{body}\n```"


def _output_body(output: nbformat.NotebookNode) -> tuple[str, str]:
    """Return (label, text_body) for one output. Non-text outputs get a
    short summary line instead of full bytes (PNGs etc. are huge in JSON).
    """
    otype = output.get("output_type", "unknown")
    if otype == "stream":
        return f"stream {output.get('name', '?')}", output.get("text", "")
    if otype == "error":
        label = f"error {output.get('ename', '?')}"
        evalue = output.get("evalue", "")
        tb = output.get("traceback", "")
        if isinstance(tb, list):
            tb = "\n".join(tb)
        # evalue is the short message; traceback is the long body. Concatenate
        # so --out-offset/--out-limit slice the entire error text as one stream.
        body = evalue
        if tb:
            body = f"{evalue}\n{tb}" if evalue else tb
        return label, body
    if otype in ("execute_result", "display_data"):
        data = output.get("data", {}) or {}
        if "text/plain" in data:
            body = data["text/plain"]
            if isinstance(body, list):
                body = "".join(body)
            return otype, body
        # Non-text output — summarize (do NOT dump base64).
        for mime in ("image/png", "image/jpeg", "image/svg+xml"):
            if mime in data:
                return mime, f"[{mime}, {len(str(data[mime]))} chars — not shown]"
        if "text/html" in data:
            body = data["text/html"]
            if isinstance(body, list):
                body = "".join(body)
            return "text/html", body
        mimes = ", ".join(data.keys()) or "no data"
        return otype, f"[unsupported mimetypes: {mimes}]"
    return otype, f"[unsupported output_type: {otype}]"


def _parse_index_spec(spec: str, total: int) -> list[int]:
    """Parse `wt cat --index` value into a list of 0-based cell indices.

    Forms (Python-slice-style, half-open):
      'N'     -> [N]               single cell
      'N:M'   -> N, N+1, ..., M-1  inclusive start, exclusive end
      ':M'    -> 0, 1, ..., M-1
      'N:'    -> N, N+1, ..., end
    Negative N/M count from the end (like Python). Bounds-checked.
    """
    spec = spec.strip()
    if ":" in spec:
        a, b = spec.split(":", 1)
        start = int(a) if a.strip() else 0
        end = int(b) if b.strip() else total
        if start < 0:
            start += total
        if end < 0:
            end += total
        if not (0 <= start <= end <= total):
            raise ValueError(
                f"index range {spec!r} out of bounds (notebook has {total} cells)."
            )
        return list(range(start, end))
    n = int(spec)
    if n < 0:
        n += total
    if not (0 <= n < total):
        raise ValueError(f"index {spec} out of bounds (notebook has {total} cells).")
    return [n]


def _matching_indices(
    nb: nbformat.NotebookNode,
    *,
    index: int | str | None,
    tag: str | None,
    label: str | None,
) -> list[int]:
    """Indices of cells matching the locator; may be empty or many.

    Exactly one of `index` / `tag` / `label` must be given. `index` may
    be an int (single cell) or a slice spec string ('N', 'N:M', ':M', 'N:')
    expanded against `len(nb["cells"])`.
    """
    if sum(x is not None for x in (index, tag, label)) != 1:
        raise ValueError("pass exactly one of --index / --tag / --label.")
    if index is not None:
        if isinstance(index, str):
            return _parse_index_spec(index, len(nb["cells"]))
        if not (0 <= index < len(nb["cells"])):
            raise ValueError(
                f"index {index} out of bounds (notebook has {len(nb['cells'])} cells)."
            )
        return [index]
    return [
        i
        for i, c in enumerate(nb["cells"])
        if (tag is not None and tag in cell_tags(c))
        or (label is not None and _cell_label(c) == label)
    ]


def _resolve_unique_cell(
    nb: nbformat.NotebookNode,
    *,
    index: int | None,
    tag: str | None,
    label: str | None,
) -> int:
    """Resolve to exactly one cell index. Error if ambiguous or missing."""
    matches = _matching_indices(nb, index=index, tag=tag, label=label)
    if not matches:
        raise ValueError(
            f"no cell matched (index={index}, tag={tag}, label={label})."
        )
    if len(matches) > 1:
        idxs = ", ".join(str(m) for m in matches)
        raise ValueError(
            f"ambiguous: {len(matches)} cells matched (indices {idxs}). "
            "narrow with --index or a unique --label."
        )
    return matches[0]


# ---Public operations ----------------------------------------------------


def count_cells(name: str) -> int:
    """Return the number of cells in a notebook."""
    path = resolve_ipynb(name)
    nb = read_notebook(path)
    return len(nb["cells"])


def cat_notebook(
    name: str,
    *,
    index: int | str | None = None,
    tag: str | None = None,
    label: str | None = None,
    offset: int = 0,
    limit: int | None = None,
    with_outputs: bool = False,
    out_offset: int = 0,
    out_limit: int | None = None,
    context: int = 0,
    decode_solutions: bool = False,
) -> str:
    """Render notebook cell sources as markdown.

    Without a filter: all cells. With a locator: matching cells only
    (a tag may legitimately hit multiple; index/label usually hit one).

    --offset/--limit slice the matched cell source (char-wise).
    --with-outputs appends each matched code cell's outputs, each with its
    own header. --out-offset/--out-limit slice each output's text body.
    Output slicing is per-output (each output starts fresh at out_offset).

    --context N expands a locator to include the N cells before the first
    match and after the last (context cells carry a `context` marker in
    their header). --decode-solutions replaces the stored source of
    solution-tagged cells with its decoded plaintext.
    """
    path = resolve_ipynb(name)
    nb = read_notebook(path)

    def render(i: int, *, context: bool = False) -> str:
        return _render_cell(
            nb["cells"][i], i,
            offset=offset, limit=limit,
            with_outputs=with_outputs,
            out_offset=out_offset, out_limit=out_limit,
            context=context, decode_solutions=decode_solutions,
        )

    if index is None and tag is None and label is None:
        return "\n\n".join(render(i) for i in range(len(nb["cells"])))
    idxs = _matching_indices(nb, index=index, tag=tag, label=label)
    if not idxs:
        raise ValueError(
            f"no cell matched in '{name}' "
            f"(index={index}, tag={tag}, label={label})."
        )
    if context:
        lo = max(0, min(idxs) - context)
        hi = min(len(nb["cells"]), max(idxs) + context + 1)
        matched = set(idxs)
        return "\n\n".join(
            render(i, context=i not in matched) for i in range(lo, hi)
        )
    return "\n\n".join(render(i) for i in idxs)


def edit_cell(
    name: str,
    source: str,
    *,
    index: int | None = None,
    tag: str | None = None,
    label: str | None = None,
) -> Path:
    """Replace a single cell's source in-place, preserving outputs/metadata.

    Exactly one of --index/--tag/--label is required. Errors if the locator
    matches zero or multiple cells.
    """
    path = resolve_ipynb(name)
    nb = read_notebook(path)
    i = _resolve_unique_cell(nb, index=index, tag=tag, label=label)
    check_source_limit(source)
    nb["cells"][i]["source"] = source
    nbformat.write(nb, path)
    return path


def _new_cell(cell_type: str, source: str) -> nbformat.NotebookNode:
    ct = _normalize_cell_type(cell_type)
    if ct == CELL_TYPE_MD:
        return nbformat.v4.new_markdown_cell(source)
    return nbformat.v4.new_code_cell(source)


def append_cell(
    name: str, source: str, *, cell_type: str = CELL_TYPE_MD
) -> Path:
    """Append a new cell to the end of the notebook."""
    path = resolve_ipynb(name)
    nb = read_notebook(path)
    check_source_limit(source)
    nb["cells"].append(_new_cell(cell_type, source))
    nbformat.write(nb, path)
    return path


def insert_cell(
    name: str,
    source: str,
    *,
    after: int | None = None,
    before: int | None = None,
    tag: str | None = None,
    label: str | None = None,
    cell_type: str = CELL_TYPE_MD,
) -> Path:
    """Insert a new cell above/below a located cell.

    Pass --after (preferred) or --before as a 0-based index, or use --tag /
    --label (must resolve to exactly one cell). Exactly one locator must
    be provided.
    """
    if sum(x is not None for x in (after, before, tag, label)) != 1:
        raise ValueError("pass exactly one of --after / --before / --tag / --label.")
    check_source_limit(source)
    path = resolve_ipynb(name)
    nb = read_notebook(path)
    if after is not None:
        position = after + 1
    elif before is not None:
        position = before
    else:
        position = _resolve_unique_cell(nb, index=None, tag=tag, label=label) + 1
    if not (0 <= position <= len(nb["cells"])):
        raise ValueError(
            f"insert position {position} out of range "
            f"(notebook has {len(nb['cells'])} cells)."
        )
    nb["cells"].insert(position, _new_cell(cell_type, source))
    nbformat.write(nb, path)
    return path


def remove_cell(
    name: str,
    *,
    index: int | None = None,
    tag: str | None = None,
    label: str | None = None,
) -> Path:
    """Remove cells matching the locator. A tag may remove multiple.

    Errors if nothing matched.
    """
    path = resolve_ipynb(name)
    nb = read_notebook(path)
    idxs = _matching_indices(nb, index=index, tag=tag, label=label)
    if not idxs:
        raise ValueError(
            f"no cell matched (index={index}, tag={tag}, label={label})."
        )
    for i in sorted(idxs, reverse=True):
        del nb["cells"][i]
    nbformat.write(nb, path)
    return path


def clear_outputs(
    name: str,
    *,
    index: int | None = None,
    tag: str | None = None,
    label: str | None = None,
    from_index: int | None = None,
) -> Path:
    """Clear stored outputs of code cells matching the locator.

    Locator precedence: --from N clears every code cell from index N to the
    end (useful for a trailing section like a problem set); --index / --tag /
    --label clear the matching cells (a tag may match multiple); with no
    locator, every code cell in the notebook is cleared. Errors if no code
    cell matched. Markdown cells are skipped.
    """
    path = resolve_ipynb(name)
    nb = read_notebook(path)
    if from_index is not None:
        if not (0 <= from_index < len(nb["cells"])):
            raise ValueError(
                f"from-index {from_index} out of bounds "
                f"(notebook has {len(nb['cells'])} cells)."
            )
        idxs = list(range(from_index, len(nb["cells"])))
    elif index is not None or tag is not None or label is not None:
        idxs = _matching_indices(nb, index=index, tag=tag, label=label)
    else:
        idxs = list(range(len(nb["cells"])))
    code_idxs = [i for i in idxs if nb["cells"][i]["cell_type"] == "code"]
    if not code_idxs:
        raise ValueError(
            f"no code cell matched (index={index}, tag={tag}, label={label}, "
            f"from_index={from_index})."
        )
    for i in code_idxs:
        nb["cells"][i]["outputs"] = []
    nbformat.write(nb, path)
    return path


def tag_cell(
    name: str,
    *,
    index: int | None = None,
    tag: str | None = None,
    label: str | None = None,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> Path | list[str]:
    """Add and/or remove tags from a single cell.

    Exactly one of --index/--tag/--label is required (must match a unique
    cell). If neither `add` nor `remove` is given, returns current tags
    without modifying the notebook.
    """
    path = resolve_ipynb(name)
    nb = read_notebook(path)
    i = _resolve_unique_cell(nb, index=index, tag=tag, label=label)
    cell = nb["cells"][i]
    existing = list(cell.get("metadata", {}).get("tags", []))
    if not add and not remove:
        return existing
    s = set(existing)
    for t in (remove or []):
        s.discard(t)
    for t in (add or []):
        s.add(t)
    new_tags = sorted(s)
    cell.setdefault("metadata", {})["tags"] = new_tags
    nbformat.write(nb, path)
    return path


# ---wt diff-----------------------------------------------------------------


def _git_root() -> Path:
    """Repo root via `git rev-parse --show-toplevel`, or ValueError."""
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise ValueError(
            "not inside a git repository — `wt diff` needs git to read the base version"
        )
    return Path(proc.stdout.strip())


def diff_notebook(name: str, base: str = "HEAD") -> str | None:
    """Markdown diff of a notebook against a git ref (default HEAD).

    Both sides are rendered with the same JSON-stripped cell rendering used
    by ``wt cat`` (no outputs), so the diff shows content changes, not
    `.ipynb` JSON noise. Solution-tagged cells are decoded on both sides so
    content edits to an encoded solution show up as readable diff lines.

    Returns the unified diff, or None when the notebook is unchanged.
    """
    path = resolve_ipynb(name)
    root = _git_root()
    rel = path.resolve().relative_to(root)
    ls = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(rel)],
        capture_output=True, text=True,
    )
    if ls.returncode != 0:
        raise ValueError(f"{rel} is not tracked by git (new file — nothing to diff).")
    proc = subprocess.run(
        ["git", "show", f"{base}:{rel}"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout).strip().splitlines()
        detail = err[-1] if err else "unknown error"
        raise ValueError(f"can't read {rel} at ref '{base}': {detail}")
    old_nb = nbformat.reads(proc.stdout, as_version=nbformat.NO_CONVERT)
    new_nb = read_notebook(path)

    def render(nb: nbformat.NotebookNode) -> list[str]:
        lines: list[str] = []
        for i, c in enumerate(nb["cells"]):
            block = _render_cell(c, i, limit=None, decode_solutions=True)
            lines.extend(block.splitlines())
        return lines

    old_lines = render(old_nb)
    new_lines = render(new_nb)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"{base}:{rel}", tofile=str(rel), n=2, lineterm="",
    )
    out = "\n".join(diff)
    return out or None