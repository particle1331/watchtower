"""Trivial reversible obfuscation for course solution cells.

Solutions live in the chapter notebooks as code cells tagged ``solution`` +
the problem id (e.g. ``07-3``). The cell source starts with Quarto cell
options that hide the cell entirely from the rendered site::

    #| echo: false
    #| eval: false
    #| output: false

followed by the ROT18-encoded solution body with each non-empty line
prefixed ``# `` (blank lines stay blank). ROT18 is ROT13 over ASCII letters
plus ROT5 over ASCII digits; it keeps the cells unreadable at a glance while
studying in JupyterLab, and unreadable digits hide the numeric answers that
plain ROT13 would leak. The encoding is an involution, so ``deobfuscate`` is
``obfuscate``; it is not security, just a spoiler guard. ``wt solution`` /
``wt hint`` decode on read; ``wt solution-edit`` encodes on write; ``wt check``
verifies that no solution cell was accidentally committed in plaintext.
"""


_ROT13 = str.maketrans(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "nopqrstuvwxyzabcdefghijklmNOPQRSTUVWXYZABCDEFGHIJKLM",
)
_ROT5 = str.maketrans("0123456789", "5678901234")

#: Quarto cell options that hide a solution code cell from the rendered site
#: (echo:false hides input, eval:false prevents execution, output:false hides
#: output). The option lines stay literal (unencoded).
OPTIONS_HEADER = "#| echo: false\n#| eval: false\n#| output: false"


def obfuscate(text: str) -> str:
    """ROT18: shift ASCII letters by 13 and ASCII digits by 5."""
    return text.translate(_ROT13).translate(_ROT5)


def deobfuscate(text: str) -> str:
    """Inverse of :func:`obfuscate` (ROT18 is an involution)."""
    return obfuscate(text)


def wrap(plaintext: str) -> str:
    """Encode ``plaintext`` and wrap it in the solution cell format.

    Returns the ``#|`` Quarto options header followed by the ROT18-encoded
    body with each non-empty line prefixed ``# `` (blank lines stay blank).
    """
    encoded = obfuscate(plaintext)
    body = "\n".join(
        f"# {line}" if line.strip() else line
        for line in encoded.splitlines()
    )
    return f"{OPTIONS_HEADER}\n{body}"


def unwrap(source: str) -> str:
    """Strip the ``#|`` options header and ``# `` line prefixes from a
    solution cell source, returning the ROT18 body (still encoded).

    Tolerates a missing header (returns the body as-is) so that reads still
    work before a fix; ``wt check`` flags unwrapped cells.
    """
    lines = source.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and lines[0].strip().startswith("#|"):
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return "\n".join(
        line[2:] if line.startswith("# ") else line
        for line in lines
    )


def is_wrapped(source: str) -> bool:
    """True when the source starts with the ``#|`` options header."""
    for line in source.splitlines():
        if not line.strip():
            continue
        return line.strip().startswith("#|")
    return False