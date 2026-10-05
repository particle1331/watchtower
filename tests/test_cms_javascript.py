"""Browser enhancement behavior can be checked without optional browser drivers."""

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(not shutil.which("node"), reason="JavaScript behavior checks require Node")
def test_cms_javascript_behaviors():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", "--test", "tests/javascript/cms.test.cjs"], cwd=root, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
