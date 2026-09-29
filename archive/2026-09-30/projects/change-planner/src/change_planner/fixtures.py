"""Small pinned repositories and change scenarios for deterministic evaluation."""

from change_planner.schemas import ChangeRequest, EvaluationCase, FixtureSource, RepositorySnapshot

REPOSITORY = "fixture/change-cli"
REVISION = "8f2c1d"

_SOURCE_ROWS = [
    {
        "id": "commands",
        "source_kind": "code",
        "path": "src/change_cli/commands.py",
        "tags": ["clear outputs", "cli", "side effect", "dry run"],
        "symbols": ["clear_outputs", "remove_output", "run_command"],
        "related_tests": ["test_clear_outputs", "test_preserves_solution_cells"],
        "related_sources": ["notebook_ops", "test_clear_outputs", "commands_docs"],
        "text": """def clear_outputs(notebook, start=None, dry_run=False):
    targets = notebook.code_cells[start:]
    if dry_run:
        return [cell.index for cell in targets]
    for cell in targets:
        if cell.metadata.get('solution'):
            continue
        remove_output(cell)

def remove_output(cell):
    cell.outputs = []
""",
    },
    {
        "id": "notebook_ops",
        "source_kind": "code",
        "path": "src/change_cli/notebook_ops.py",
        "tags": ["notebook", "outputs", "solution cells", "mutation"],
        "symbols": ["remove_output", "is_solution_cell"],
        "related_tests": ["test_preserves_solution_cells"],
        "related_sources": ["commands", "test_clear_outputs"],
        "text": """def is_solution_cell(cell):
    return 'solution' in cell.metadata.get('tags', [])

def remove_output(cell):
    if is_solution_cell(cell):
        return False
    cell.outputs = []
    return True
""",
    },
    {
        "id": "test_clear_outputs",
        "source_kind": "test",
        "path": "tests/test_clear_outputs.py",
        "tags": ["clear outputs", "dry run", "solution cells", "regression"],
        "symbols": ["test_clear_outputs", "test_preserves_solution_cells", "test_dry_run"],
        "related_sources": ["commands", "notebook_ops"],
        "text": """def test_clear_outputs_removes_regular_outputs():
    result = clear_outputs(notebook)
    assert result == [0, 1]

def test_preserves_solution_cells():
    clear_outputs(notebook)
    assert solution_cell.outputs == original_outputs

def test_dry_run_has_no_side_effects():
    before = snapshot(notebook)
    clear_outputs(notebook, dry_run=True)
    assert snapshot(notebook) == before
""",
    },
    {
        "id": "commands_docs",
        "source_kind": "docs",
        "path": "docs/commands.md",
        "tags": ["clear outputs", "dry run", "cli contract"],
        "symbols": ["clear-outputs", "--dry-run", "--from"],
        "related_sources": ["commands", "test_clear_outputs"],
        "text": """# clear-outputs

`wt clear-outputs NOTEBOOK --from N` clears regular code-cell outputs.
Solution-tagged cells are never modified. `--dry-run` lists the cells that
would change and must not write the notebook.
""",
    },
    {
        "id": "pyproject",
        "source_kind": "config",
        "path": "pyproject.toml",
        "tags": ["cli", "entry point", "configuration"],
        "symbols": ["clear-outputs", "change-cli"],
        "related_sources": ["commands", "commands_docs"],
        "text": """[project.scripts]
change-cli = \"change_cli.cli:main\"

[tool.pytest.ini_options]
testpaths = [\"tests\"]
""",
    },
    {
        "id": "history_dry_run",
        "source_kind": "git",
        "path": "git/8f2c1d.patch",
        "tags": ["dry run", "clear outputs", "history", "side effect"],
        "symbols": ["clear_outputs"],
        "related_sources": ["commands", "test_clear_outputs"],
        "text": """commit 8f2c1d
Add a dry-run branch before the first notebook mutation. The change was made
after a user reported that preview commands unexpectedly changed outputs.
The regression fix added test_dry_run and preserved test_preserves_solution_cells.
""",
    },
    {
        "id": "retry_client",
        "source_kind": "code",
        "path": "src/change_cli/client.py",
        "tags": ["retry", "timeout", "side effect", "client"],
        "symbols": ["request_with_retry", "MAX_ATTEMPTS"],
        "related_tests": ["test_retry_limit"],
        "related_sources": ["test_retry_limit", "history_retry"],
        "text": """MAX_ATTEMPTS = 3

def request_with_retry(send, request):
    for attempt in range(MAX_ATTEMPTS):
        try:
            return send(request)
        except TimeoutError:
            if attempt == MAX_ATTEMPTS - 1:
                raise
""",
    },
    {
        "id": "test_retry_limit",
        "source_kind": "test",
        "path": "tests/test_retry_limit.py",
        "tags": ["retry", "timeout", "regression"],
        "symbols": ["test_retry_limit", "test_no_duplicate_write"],
        "related_sources": ["retry_client"],
        "text": """def test_retry_limit():
    assert attempts_for_timeout() == 3

def test_no_duplicate_write():
    assert retrying_write_is_idempotent()
""",
    },
    {
        "id": "history_retry",
        "source_kind": "git",
        "path": "git/7ac921.patch",
        "tags": ["retry", "history", "regression"],
        "symbols": ["request_with_retry"],
        "related_sources": ["retry_client", "test_retry_limit"],
        "text": """commit 7ac921
An earlier retry increase caused duplicate writes when the server completed
the request but the response timed out. The fix required idempotency keys and
an explicit test for no_duplicate_write.
""",
    },
]


def load_sources() -> list[FixtureSource]:
    return [FixtureSource(repository=REPOSITORY, revision=REVISION, **row) for row in _SOURCE_ROWS]


def snapshot() -> RepositorySnapshot:
    return RepositorySnapshot(
        repository=REPOSITORY,
        revision=REVISION,
        index_id="fixture-index-v1",
        source_fingerprint="sha256:fixture-change-cli-8f2c1d",
    )


def request_for(scenario_id: str) -> ChangeRequest:
    requests = {
        "dry-run-01": ChangeRequest(
            scenario_id="dry-run-01",
            repository=REPOSITORY,
            revision=REVISION,
            request="Add a dry-run mode to clear-outputs without changing the default behavior or solution cells.",
            scope=["src/change_cli", "tests", "docs", "pyproject.toml"],
            execution_policy="allow_targeted_tests",
        ),
        "retry-01": ChangeRequest(
            scenario_id="retry-01",
            repository=REPOSITORY,
            revision=REVISION,
            request="Increase client retries for production timeouts without causing duplicate writes.",
            scope=["src/change_cli/client.py", "tests/test_retry_limit.py", "git"],
            execution_policy="allow_targeted_tests",
        ),
        "dry-run-02": ChangeRequest(
            scenario_id="dry-run-02",
            repository=REPOSITORY,
            revision=REVISION,
            request="Which tests and files must be checked before making clear-outputs support dry-run?",
            scope=["src/change_cli", "tests", "docs", "pyproject.toml"],
            execution_policy="allow_targeted_tests",
        ),
        "retry-02": ChangeRequest(
            scenario_id="retry-02",
            repository=REPOSITORY,
            revision=REVISION,
            request="Which evidence should be reviewed before increasing timeout retries?",
            scope=["src/change_cli/client.py", "tests/test_retry_limit.py", "git"],
            execution_policy="allow_targeted_tests",
        ),
    }
    try:
        return requests[scenario_id]
    except KeyError as exc:
        raise KeyError(f"unknown fixture scenario: {scenario_id}") from exc


def load_cases() -> list[EvaluationCase]:
    return [
        EvaluationCase(
            id="dry-run-01",
            category="behavior",
            tier="worked",
            question="What would change if clear-outputs gained a dry-run flag?",
            request=request_for("dry-run-01"),
            expected_sources=["commands", "test_clear_outputs", "commands_docs", "history_dry_run"],
            expected_tests=["test_clear_outputs"],
            expected_symbols=["clear_outputs", "test_dry_run", "test_preserves_solution_cells"],
        ),
        EvaluationCase(
            id="retry-01",
            category="regression",
            tier="validation",
            question="What could break if timeout retries increase?",
            request=request_for("retry-01"),
            expected_sources=["retry_client", "test_retry_limit", "history_retry"],
            expected_tests=["test_retry_limit"],
            expected_symbols=["request_with_retry", "test_no_duplicate_write"],
            seeded_regression=True,
        ),
        EvaluationCase(
            id="dry-run-02",
            category="behavior",
            tier="challenge",
            question="Which tests and files must be checked before making clear-outputs support dry-run?",
            request=request_for("dry-run-02"),
            expected_sources=["commands", "test_clear_outputs", "commands_docs"],
            expected_tests=["test_clear_outputs"],
            expected_symbols=["clear_outputs", "test_dry_run"],
        ),
        EvaluationCase(
            id="retry-02",
            category="configuration",
            tier="challenge",
            question="Which evidence should be reviewed before increasing timeout retries?",
            request=request_for("retry-02"),
            expected_sources=["retry_client", "test_retry_limit", "history_retry"],
            expected_tests=["test_retry_limit"],
            expected_symbols=["request_with_retry", "test_no_duplicate_write"],
        ),
    ]


def case_for(scenario_id: str) -> EvaluationCase:
    return next(case for case in load_cases() if case.id == scenario_id)
