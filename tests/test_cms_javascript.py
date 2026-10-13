"""Browser enhancement behavior can be checked without optional browser drivers."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="JavaScript behavior checks require Node")
@pytest.mark.parametrize("script", ["cms", "plan"])
def test_cms_javascript_behaviors(script):
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", "--test", f"tests/javascript/{script}.test.cjs"], cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
