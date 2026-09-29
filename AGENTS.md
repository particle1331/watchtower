# Watchtower agent instructions

## Boundaries and sources of truth

Active knowledge work is registered in `knowledge/catalog.yaml`. It contains logical posts, courses, chapters, portfolio pieces, and projects, with stable IDs, paths, visibility, lifecycle, and relationships. `nb/photos/photos.ipynb` remains a separate personal gallery. Operational code in `src/` and `scripts/`, plus résumé sources, is outside the knowledge catalog.

The former posts, courses, portfolio, and projects live under `archive/2026-09-30/`. They are source material, not active content or published pages. Use `wt map --archive`, `wt ls <tier> --archive`, or `wt find <query> --archive` deliberately. Do not silently use archived claims as current facts.

For a course, read context in this order:

1. `wt context <artifact-id-or-path>` for the catalog record, the course YAML, and reading paths.
2. `course.yaml` for purpose, audience, the **planned** path, and the separately maintained **actualized** account.
3. `index.ipynb` for the learner-facing course home (the course README).
4. Optional `00-overview.ipynb` for the deeper whole-course technical design.
5. The target chapter. Read adjacent chapter openings only for a relevant handoff. Do not load all sibling notebooks by default.

A plan in YAML is intent, not evidence of completion. Update `actualized` only when work has been completed and checked. Course YAML holds concise facts shared by agents and readers; detailed teaching and practical instructions belong in notebooks. The course home includes a generated Markdown rendering of those shared facts. Run `make knowledge` or the regular render tasks after YAML changes.
Only artifacts with `visibility: public` and `lifecycle: published` are added to Quarto's render list by `wt sync-site`; `make knowledge` validates and runs that synchronization. Publishing a course renders its home, creates a grid card on the generated Courses page, and adds the shared navbar link. Chapters are published and rendered individually under a published course; synchronization filters unpublished chapters out of that course's sidebar. The authored course outline is stored in `knowledge/sidebar.yaml`; `_quarto.yml` contains its synchronized published view. Use `wt publish <course-or-chapter-id>` to publish one public catalog entry without changing its siblings.

## Navigation and notebooks

Run `.venv/bin/wt map` first. The venv is required; never run bare `wt`. `wt map`, `wt ls`, and default `wt find` use only the active catalog. Run `wt validate` to catch missing references and unregistered active files. `wt context` gives course-level context; `wt cat --context N` gives only neighboring **cells within one notebook**.

Notebook source is canonical `.ipynb`, edited in JupyterLab and rendered by Quarto with stored outputs, without re-execution. Do not grep or edit raw notebook JSON. Use `wt find <query>` to get a path and cell index, `wt cat <name> --index N --context 3` to inspect it, then `wt edit-cell`, `append-cell`, `insert-cell`, or `remove-cell`. `wt cat` accepts an ID, bare stem, tier-prefixed stem, or full path. It supports `--index N|N:M`, `--tag`, `--label`, `--offset`, `--limit`, and `--with-outputs`. The default source limit is 4096 characters per cell; `--limit 0` is unlimited.

Cell mutations use exactly one locator. Insertions and removals shift later indices, so re-read after structural edits. Cell writes are capped at 20,000 source characters. Review with `wt diff`, run edited code cells with `wt run <name> --index N`, and inspect stored results with `wt output`. A notebook with no code cells needs no kernel run. Use `wt kernels` to discover kernels.

## Creation and catalog maintenance

`wt new post`, `wt new course`, `wt new chapter`, and `wt import` register the content they create. A new course also gets `course.yaml`, `index.ipynb`, a first chapter, a generated context include, and sidebar registration. `wt new section` changes sidebar grouping. `wt publish <course-or-chapter-id>` publishes that public entry and synchronizes the site; publish a course first, then publish chapters as they are ready. `make project` registers a new project; use `wt register` for an existing project or portfolio piece. Run `wt validate` afterward. `wt render-context` regenerates includes and `wt sync-site` synchronizes public published pages. Update both this file and `README.md` whenever the CLI surface changes.

The site publishes public, published catalog entries alongside the home, résumé, and photo gallery; new knowledge content must be registered before discovery. `make knowledge` refreshes course includes, `make resume` rebuilds generated résumé artifacts, `make docs PORT=4300` previews the site, and `make render NOTEBOOK=<path>` renders a PDF. Scratch files belong in the repo's `.tmp/`, not system `/tmp`. `make project NAME=<name>` scaffolds a uv workspace member. `make bootstrap` runs `make setup-skills` before `uv sync`.

Shared skills have canonical sources under `skills/`; `.codex/skills/` and `.opencode/skills/` are links. Edit canonical skill files and run `make setup-skills` when creating a skill. Load `skills/course-builder/SKILL.md` for course-level work and the notebook writing and Quarto skills for notebook content.

For new courses or multi-file course revisions, use an isolated Git worktree when the environment permits and preview it on a separate port, usually 4300. Never reset or overwrite a dirty primary checkout. For Python changes under `src/` or `projects/`, run `make lint` and `make typecheck`; use `make test` for behavior changes. Archived projects are excluded from active lint and type checking.

If `wt` lacks a needed notebook operation or fails on a supported notebook, do not manipulate raw JSON. Explain the command, the gap or failure, and the expected result, then ask the user whether they want an issue filed. Keep secrets in the OS keyring through `wt vault`; never commit them or print values in tool output. Prefer plain prose and use em dashes sparingly.
