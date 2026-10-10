"""Mechanical drift audit (Step 06). Run from toy-project/: python3 tools/audit.py

Reports: unused imports, duplicated timedelta logic, and modules named in ARCHITECTURE.md
that do not exist. It cannot judge duplicated *concepts*; that needs a human reader.
"""

import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def unused_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names += [(a.asname or a.name).split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            names += [a.asname or a.name for a in node.names]
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    return [n for n in names if n not in used and n != "annotations"]


def main():
    problems = 0
    for path in sorted(ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        unused = unused_imports(path)
        if unused:
            problems += 1
            print(f"unused import in {path.relative_to(ROOT)}: {unused}")
    for path in sorted((ROOT / "habits").rglob("*.py")):
        if "timedelta" in path.read_text(encoding="utf-8"):
            print(f"timedelta logic in {path.relative_to(ROOT)} (check it is not duplicated)")
    doc = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
    layout = doc.split("```")[3] if doc.count("```") >= 4 else ""
    for name in sorted(set(re.findall(r"^\s{4,6}(\w+\.py)\s", layout, flags=re.M))):
        if not list(ROOT.rglob(name)):
            problems += 1
            print(f"documented but missing: {name}")
    print("audit: clean" if not problems else f"audit: {problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
