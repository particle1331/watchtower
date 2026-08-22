.PHONY: bootstrap setup-skills test lint typecheck review

bootstrap: setup-skills
	uv sync
	@echo "Ready. Try: wt --help"

setup-skills:
	./scripts/setup-skills

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
