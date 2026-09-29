import sys
from pathlib import Path

from change_planner.verification import run_targeted_test


def test_targeted_test_requires_explicit_authorization(tmp_path: Path) -> None:
    result = run_targeted_test(
        tmp_path,
        [sys.executable, "-c", "print('should not run')"],
        authorized=False,
    )

    assert result.status == "blocked"
    assert result.returncode is None
    assert result.output_fingerprint.startswith("sha256:")


def test_targeted_test_records_result_and_output_fingerprint(tmp_path: Path) -> None:
    result = run_targeted_test(
        tmp_path,
        [sys.executable, "-c", "print('verified')"],
        authorized=True,
    )

    assert result.status == "passed"
    assert result.returncode == 0
    assert result.stdout.strip() == "verified"
    assert result.output_fingerprint.startswith("sha256:")
    assert result.cwd == str(tmp_path.resolve())


def test_targeted_test_blocks_shell_interpreters(tmp_path: Path) -> None:
    result = run_targeted_test(
        tmp_path,
        ["sh", "-c", "echo unsafe"],
        authorized=True,
    )

    assert result.status == "blocked"
    assert "not allowed" in result.reason
