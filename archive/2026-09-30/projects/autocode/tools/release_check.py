"""Release checklist that can run without network access."""

from pathlib import Path

REQUIRED = ("README.md", "pyproject.toml", "docs/quickstart.md", "deploy/Dockerfile")


def check(root: str | Path = ".") -> list[str]:
    root = Path(root)
    return [name for name in REQUIRED if not (root / name).exists()]


if __name__ == "__main__":
    missing = check(Path(__file__).parents[1])
    if missing:
        raise SystemExit(f"missing release files: {', '.join(missing)}")
    print("release checklist: ready")
