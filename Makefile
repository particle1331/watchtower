.PHONY: sync check preview publish render test lint typecheck install-hooks bootstrap

bootstrap:
	uv sync
	pre-commit install
	@echo "Ready. Try: wt --help"

install-hooks:
	pre-commit install

sync:
	uv run wt sync

check:
	uv run wt check

preview:
	uv run wt preview

publish:
	uv run wt publish

render:
	@if [ -z "$(F)" ]; then echo "usage: make render F=notes/src/foo.ipynb"; exit 2; fi
	uv run wt render $(F)

test:
	uv run pytest

lint:
	uv run ruff check .

typecheck:
	uv run pyright