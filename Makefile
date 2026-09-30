.PHONY: help bootstrap setup-skills test lint typecheck review resume knowledge docs render project preview build cms mcp

.DEFAULT_GOAL := help
PYTHON := .venv/bin/python
PORT ?= 4200
export PORT NAME NOTEBOOK

help:
	@echo "Notebooks: .venv/bin/wt --help"
	@echo "Site:      make docs [PORT=4200], make resume, make render NOTEBOOK=<path>"
	@echo "Publishing: make preview [PORT=4300], make build, make cms"
	@echo "Projects:  .venv/bin/wt ls projects, make project NAME=my-project"
	@echo "Secrets:   .venv/bin/wt vault --help"
	@echo "Dev:       make bootstrap, setup-skills, test, lint, typecheck, review"

bootstrap: setup-skills
	uv sync
	@echo "Ready. Try: wt --help"

setup-skills:
	./scripts/setup-skills

test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check .

typecheck:
	.venv/bin/pyright

review:
	@.venv/bin/ruff check .
	@.venv/bin/pyright
	@.venv/bin/pytest
	@echo "--- diff shape ---"
	@git diff --stat

# Site artifacts are refreshed before every preview, including the résumé PDF.
resume:
	@$(PYTHON) scripts/resume.py

knowledge:
	@$(PYTHON) -m watchtower.cli render-context
	@$(PYTHON) -m watchtower.cli validate
	@$(PYTHON) -m watchtower.cli sync-site

docs: resume knowledge
	@$(PYTHON) scripts/docs.py

render: knowledge
	@$(PYTHON) scripts/render.py

project:
	@$(PYTHON) scripts/project.py

preview:
	@$(PYTHON) -m watchtower.cli preview --port $(PORT)

build:
	@$(PYTHON) -m watchtower.cli build --mode production

cms:
	@$(PYTHON) -m watchtower.cli serve --port 8000

mcp:
	@$(PYTHON) -m watchtower.cli mcp
