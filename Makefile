.PHONY: bootstrap test lint typecheck review

bootstrap:
	uv sync
	@echo "Ready. Try: wt --help"

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run pyright

review:
	@uv run ruff check .
	@uv run pyright
	@uv run pytest
	@echo "--- diff shape ---"
	@git diff --stat