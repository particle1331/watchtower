from __future__ import annotations

from agent_harness.config import ApprovalPolicy, Config
from agent_harness.safety import ApprovalManager, CommandVerdict, LoopDetector
from agent_harness.tools.base import Tool, ToolInvocation, ToolKind, ToolResult


class FakeTool(Tool):
    schema = {}

    def __init__(self, name: str, kind: ToolKind) -> None:
        self.name = name
        self.kind = kind

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        raise NotImplementedError


def test_command_classifier_and_approval_verdicts(tmp_path):
    manager = ApprovalManager(Config(cwd=tmp_path, approval=ApprovalPolicy.ON_REQUEST))
    shell = FakeTool("shell", ToolKind.SHELL)
    read = FakeTool("read_file", ToolKind.READ)

    assert manager.classify_command("git status") == CommandVerdict.SAFE
    assert manager.classify_command("rm -rf /tmp/example") == CommandVerdict.DANGEROUS
    assert manager.classify_command("make test") == CommandVerdict.UNKNOWN
    assert manager.needs_approval(shell, {"command": "git status"}) is False
    assert manager.needs_approval(shell, {"command": "make test"}) is True
    assert manager.needs_approval(read, {}) is False


def test_approval_policy_modes(tmp_path):
    shell = FakeTool("shell", ToolKind.SHELL)
    dangerous = {"command": "sudo reboot"}

    assert ApprovalManager(Config(cwd=tmp_path, approval=ApprovalPolicy.AUTO)).needs_approval(
        shell, dangerous
    ) is True
    assert ApprovalManager(Config(cwd=tmp_path, approval=ApprovalPolicy.YOLO)).needs_approval(
        shell, dangerous
    ) is False
    assert ApprovalManager(Config(cwd=tmp_path, approval=ApprovalPolicy.NEVER)).needs_approval(
        shell, {"command": "echo safe"}
    ) is True


def test_loop_detector_finds_repeats_and_cycles():
    detector = LoopDetector(max_repeats=3, window_size=10)
    detector.record("read_file", {"path": "a.py"})
    detector.record("read_file", {"path": "a.py"})
    detector.record("read_file", {"path": "a.py"})
    assert detector.is_looping() is True

    detector.reset()
    for action in ("a", "b", "a", "b"):
        detector.record(action)
    assert detector.detect_cycle(min_cycle_length=2, max_cycle_length=2) is not None
    assert "sequence of 2 actions" in detector.get_loop_message()
