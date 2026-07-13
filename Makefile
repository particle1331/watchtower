.PHONY: bootstrap test lint typecheck

bootstrap:
	uv sync
	@echo "Ready. Try: wt --help"

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run pyright