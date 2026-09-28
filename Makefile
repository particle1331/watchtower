.PHONY: help bootstrap setup-skills test lint typecheck review resume docs render project

.DEFAULT_GOAL := help
PYTHON := .venv/bin/python
PORT ?= 4200
export PORT NAME NOTEBOOK

help:
	@echo "Notebooks: .venv/bin/wt --help"
	@echo "Site:      make docs [PORT=4200], make resume, make render NOTEBOOK=<path>"
	@echo "Projects:  .venv/bin/wt ls projects, make project NAME=my-project"
	@echo "Secrets:   .venv/bin/wt vault --help"
	@echo "Dev:       make bootstrap, setup-skills, test, lint, typecheck, review"

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

# Site artifacts are refreshed before every preview, including the résumé PDF.
resume:
	@$(PYTHON) scripts/resume.py

docs: resume
	@$(PYTHON) scripts/docs.py

render:
	@$(PYTHON) scripts/render.py

project:
	@$(PYTHON) scripts/project.py
