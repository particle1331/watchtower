# Watchtower — agent rules

## Architecture
This repo is a personal system with three tiers of content with DIFFERENT visibility:
- `notes/*.ipynb` — atomic, focused explorations: a single definition, technique, or concept with a minimal live demo
- `articles/*.ipynb` — self-contained long-form articles and deep dives
- `courses/` — full course notes
- `projects/<name>/` — code projects (each a uv workspace member)

Canonical source files are Jupyter notebooks (`.ipynb`). Authors edit them
in JupyterLab (running cells, getting outputs); Quarto renders the notebooks
to the website using **inline outputs, no re-execution** — so heavy compute
done once in JupyterLab (or imported from Colab/Kaggle) is preserved as-is.

## Knowledge base
- The canonical knowledge base is `notes/*.ipynb`, `articles/*.ipynb`, and `courses/**/*.ipynb`.
- Raw `.ipynb` JSON is noisy — do NOT `grep`/`read` it directly. Use the
  `wt` wrappers below, which expose cell sources as plain markdown.
- `.ipynb_checkpoints/` is excluded from listings and resolution.

## Environment
- All `wt` commands require the venv. Use `.venv/bin/wt` (from repo root)
  or activate the venv first. Never run bare `wt`.
- Scratch/temp files belong in `tmp/` (repo root, gitignored) — not the
  system `/tmp`. Use it for any intermediate artifacts, drafts, or scratch
  docs you'd otherwise write outside the repo.

## Navigation
- Run `wt map` first to get structured repo layout as JSON.
- Run `wt ls notes|articles|courses|projects` for plain listings of notebooks.
- `<name>` for any cell command (`cat`, `edit-cell`, `append-cell`, `insert-cell`,
  `remove-cell`, `tag`, `count`, `render`) resolves as: bare stem (`001-testnote`),
  tier-prefixed stem (`notes/001-testnote`), or full path (`notes/001-testnote.ipynb`).

## Reading notebooks
- `wt cat <name>` — print all cells as markdown (`> cell N [code|markdown] ...` headers; `>` marks tool meta, not notebook content).
- `wt cat <name> --index N` — just cell N.
- `wt cat <name> --tag foo` — cells with Jupyter tag `foo` (may be multiple).
- `wt cat <name> --label fig-x` — cell whose first line is `#| label: fig-x`.
- `wt cat <name> --index N --offset 500 --limit 1000` — slice chars 500:1500
  of cell N's source. Header carries `src[start:end] of total` so you can
  chain reads without re-paying for bytes you've already seen.
- `wt cat <name> --index N --with-outputs` — also print the cell's outputs,
  each with its own `>> cell N output K [stream stdout|error ...]` header.
  Use `--out-offset` / `--out-limit` to slice each output's body the same
  way `--offset` / `--limit` slice the source. Image/base64 payloads are
  summarized (`[image/png, N chars — not shown]`), not dumped.
- `wt cat <name> --index N --context 3` — render cells N-3..N+3; context
  cells are marked `context` in their header. The standard way to see a cell
  with its surroundings before editing.
- `wt cat <name> --tag solution --decode` — decode solution-tagged cells to
  plaintext (spoiler opt-in; default `wt cat` shows the stored encoded
  source). `wt solution <course> <locator>` is the normal way to read one.

## Agent editing workflow (any coding agent)

The notebook ops are the agent contract for every coding agent (Copilot,
opencode, Claude Code, ...). The loop:

1. `wt ls <tier>` / `wt map` — orient.
2. `wt find <query>` — locate the text; it prints `path [cell N]: line`.
3. `wt cat <path> --index N --context 3` — read the cell with its
   surroundings (or `--tag`/`--label` when the cell has stable tags).
4. `wt edit-cell <path> --index N --content "..."` — edit (or
   insert/append/remove per the rules below).
5. `wt diff <path>` — review the change as a markdown diff vs HEAD (never
   read `.ipynb` JSON directly; `wt diff` renders both sides for you).
6. `wt run <path> --index N` — re-execute the edited cell in a fresh kernel.

## Editing notebooks
- Cell writes (`edit-cell`, `append-cell`, `insert-cell`) are hard-capped at
  20k chars per source — break large content into smaller cells.
- **Cell mutations (`edit-cell`, `insert-cell`, `remove-cell`, `tag`) take
  exactly one locator: `--index N`, `--tag foo`, or `--label foo`.**
  `--tag`/`--label` must match a unique cell (writes error on zero or
  multiple matches); prefer them over positional `--index` when the cell has
  a stable tag or Quarto label. Exception: `remove-cell --tag foo` removes
  every matching cell. To target a cell without stable tags, run `wt cat`
  and read the `> cell N ...` index from its header.
- **Indices shift after insert/remove.** Any `insert-cell` or `remove-cell`
  bumps the index of every cell that comes after the anchor by ±1. So:
  - When planning multiple mutations, do them right-to-left (highest index
    first) so earlier indices stay valid. `edit-cell` does NOT shift
    anything — it only rewrites the source of cell N.
  - After an insert/remove, do NOT reuse indices you resolved before that
    mutation — re-run `wt cat` (or `wt count`) to get fresh indices.
- `wt edit-cell <name> --index N | --tag foo | --label foo --content "..."`
  — replace a cell's source (outputs + metadata preserved). Source may come
  from `--content` or stdin (useful for multi-line via heredoc). stdin is
  always decoded as UTF-8, so piping Unicode (box-drawing, arrows, dashes,
  accents) is safe on any platform — no `PYTHONUTF8`/encoding dance needed.
- `wt append-cell <name> --type md|code [--content "..."]` — push to end.
- `wt insert-cell <name> --after N | --before N | --tag foo | --label foo
  --type md|code [--content "..."]` — insert a new cell below/above the
  located cell; `--tag`/`--label` insert *below* the matched cell.
- `wt remove-cell <name> --index N | --tag foo | --label foo` — delete the
  matching cell(s); a tag may remove multiple. To remove a range, resolve
  each index via `wt cat --tag/--label` (or `wt count` for a tail) and
  delete from highest to lowest (see index-shift rule above).
- `wt tag <name> --index N | --tag foo | --label foo --add foo --remove bar`
  — manage Jupyter cell tags (unique match required). With neither `--add`
  nor `--remove`, prints the cell's current tags.

## Executing notebooks
- `wt run <name> [--index N] [--timeout S] [--kernel K]` — execute code
  cells in-place via nbclient, writing outputs back to the `.ipynb`. Quarto
  renders inline outputs without re-running; `wt run` is the explicit
  re-execution path. Execution is JupyterLab-like: a cell error is stored as
  an inline output and execution continues; exit code is 1 if any cell
  errored (agents can use it to verify notebook code).
- `--index N` runs only that cell in a *fresh* kernel, so state from other
  cells does not carry over; a dependent cell failing is the useful signal.
- A notebook with no code cells prints "no code cells to run" and never
  launches a kernel.

## Importing notebooks
- `wt import <path.ipynb> notes|articles [<name>]` — copy a notebook produced
  elsewhere (Colab, Kaggle, a teammate) into a tier dir, preserving inline
  outputs. Quarto will render with those outputs, no re-execution.
- `wt import <path.ipynb> courses <course> [<chapter>] [--section <name>]` —
  import as a chapter of an existing course: copies to
  `courses/<course>/<chapter>.ipynb` and registers it in the course's sidebar in
  `_quarto.yml` (last section by default, or the section named by `--section`).
- Import strips a leading `# Title` heading that duplicates the frontmatter
  `title` (Quarto renders that title as the page's H1), so the imported
  notebook has one H1, not two. It only runs when the notebook has frontmatter;
  a bare `# Title` with no frontmatter is kept as-is.

## Rendering
- `wt docs` serves the site on :4200 (publishing is handled by the
  `publish.yml` GitHub Action on push to `main`).
- `wt render <tier> <name> | <path.ipynb>` renders one notebook to PDF
  (`notes/pdf/` or `articles/pdf/`) using inline outputs.
- `_quarto.yml` sets `execute.enabled: false`. Quarto never runs your
  code at render time — it uses whatever outputs already live in the `.ipynb`.

## Implementation tradeoffs
Pick the mode from the directory you're writing into.

**Tooling code (`src/`, `projects/`).** Write the simplest correct thing.
This code is mostly I/O-bound notebook/file manipulation, so readability
almost always beats CPU micro-optimization. Reach for a faster but more
complex algorithm only when the input can realistically get large enough to
matter — and when you do, say so in one line. A slightly slower but obviously
correct implementation beats a clever one that needs a comment to explain why
it works. Common traps to avoid regardless: `x in some_list` inside a loop
(use a `set`), repeated string `+=` in a loop (use `join`), and building
throwaway intermediate lists you iterate once (use a generator).

**Course & note content (`notes/`, `articles/`, `courses/`).** Here the
algorithm is often the lesson, so the priorities differ. Implement the
complexity you claim: code in a note about an O(n log n) method must actually
be that — a stray O(n²) is a teaching bug even if the outputs are right. State
the complexity when it's the point. Prefer the clearest form that still
teaches the idea, and note that showing a naive version first and then the
optimized one is a feature, not a smell — keep both when the contrast is the
lesson.

## General
- Before commit there is no hook; run `make lint` and `make typecheck` if
  you changed Python under `src/` or `projects/`.
- **Doc-drift check before committing:** any change to the `wt` CLI's
  commands, options, or output format MUST be reflected in both
  `AGENTS.md` (agent-facing) and `README.md` (user-facing). Stale docs
  are worse than no docs — `wt` CLI reference is one place agents/users
  learn the surface area without reading source code.
- Do NOT commit secret values — secrets live in the OS keyring via
  `wt vault` (see below).
- Style: avoid excessive em-dash (—) usage. Use em-dashes only when
  necessary within a paragraph (e.g., one parenthetical aside); prefer
  commas, colons, or restructured sentences otherwise.

## Tooling gaps
If you hit a rough edge the `wt` CLI doesn't cover (a missing command, a parsing error, a
locator that won't resolve, a cell operation that would clobber outputs, a
render path that breaks) — do NOT silently work around it with raw `.ipynb`
JSON or ad-hoc shell scripts. **Open an issue** with
`gh issue create -R particle1331/watchtower -t "<title>" -b "<body>"`
covering the gap, the command you ran, and what you expected.

## Per-project rules
If working inside `projects/<name>/`, also read `projects/<name>/AGENTS.md`
if present (project-specific rules stack on top of these).

## Vault (secrets)
- Secrets live in the OS keyring, accessed via `wt vault`. NEVER commit secret values.
- `wt vault export` emits export lines — projects use it via
  `eval $(wt vault export)` or `from watchtower.vault import get_secret`.

## Course problems & solutions

Problems and solutions live entirely in the course chapter notebooks — there
is no `problems.json`. The identification layer is cell tags:

- **Problem statement** — markdown cell tagged `problem` + the problem id
  (e.g. `07-3`); the heading `### [PNN.N] title` is the statement title
  (chapter from the notebook filename, number per-chapter, e.g.
  `### [P11.4] Energy retention in practice`).
- **Starter code** — the code cell immediately after the statement (optional;
  theory problems have none).
- **Solution** — code cell tagged `solution` + the same id, right after the
  starter (or the statement). Its source is a `#| echo: false` /
  `#| eval: false` / `#| output: false` Quarto cell-options header followed by
  the ROT18-obfuscated body (letters shifted by 13, digits by 5), with each
  non-empty line prefixed `# ` (blank lines stay blank). The `#|` options hide
  the cell entirely on the rendered site (echo:false hides input, eval:false
  prevents execution, output:false hides output), so solutions stay in the
  notebook for self-grading but never spoil the rendered chapters. ROT18 keeps
  solutions unreadable at a glance in JupyterLab. Obfuscation is a spoiler
  guard, not security.

The id doubles as the locator (`7.3`, `07-3`, `07 3`, `projection 3` all
resolve to the same problem). Pairing is by the shared id tag, never by
position.

**Authoring rules for agents:**

- Adding a problem: `wt add-exercise <course> <chapter> --statement ... 
  [--starter ...] --solution ...` — the only sanctioned way to create a
  problem + solution pair. It numbers the problem automatically (next in the
  chapter) and encodes the solution on write as a hidden code cell (tags
  `solution` + id), so plaintext never reaches the notebook through this path.
- Updating a solution: `wt solution-set <course> <locator> --content X`
  (plaintext in, encoded stored). Reading: `wt solution` (decodes),
  `wt hint` (progressive hint). 
- NEVER hand-write a solution cell with `edit-cell`/`insert-cell` in
  plaintext — a plaintext solution fails `wt check <course>`. If you must
  edit an existing solution cell directly, read it decoded first
  (`wt cat --tag <id> --decode`), then re-encode via `wt solution-set`.
- Run `wt check <course>` after any problem/solution work.

## CLI command reference (for the agent)
- `wt new note|article <name> [--title <title>]` — scaffold a notebook stub (note or article); <title> defaults to a placeholder derived from <name>
- `wt new project <name>` — `uv init` workspace member
- `wt new course <name> <title>` — scaffold `courses/<name>/` with an index notebook and first lesson stub; <title> becomes the display title in the index frontmatter
- `wt new chapter <course> <name> [--title <title>] [--section <name>]` — scaffold a course chapter (notebook) and register it in the course's sidebar in `_quarto.yml`; <title> defaults to a placeholder derived from <name> (sidebar text and notebook frontmatter are independent surfaces — edit either or both after scaffolding)
- `wt new section <course> <name>` — add a section header to a course's sidebar in `_quarto.yml`
- `wt map` — JSON repo structure (orientation)
- `wt ls notes|articles|courses|projects` — list sources in a tier
- `wt find <query>` — grep across `.ipynb` cell sources
- `wt count <name>` — cell count (plan ranges before `--index N:M`)
- `wt cat <name> [--index N|N:M | --tag foo | --label foo] [--offset O --limit L]
  [--with-outputs] [--out-offset O --out-limit L] [--context N] [--decode]`
  — read notebook cells as markdown. `--index` accepts a single 0-based index
  or a Python-style slice (`N:M`, `:M`, `N:`) to scan a range of cells quickly.
  Default per-cell limit is 4096 chars (`--limit 0` = unlimited).
  `--context N` also renders the N cells around each match (marked
  `context`); `--decode` decodes solution-tagged cells to plaintext.
- `wt edit-cell <name> --index N | --tag foo | --label foo [--content X]`
  — replace a cell's source (outputs + metadata preserved); locator must match one cell
- `wt append-cell <name> --type md|code [--content X]`
  — append a new cell
- `wt insert-cell <name> --after N | --before N | --tag foo | --label foo
  --type md|code [--content X]` — insert a new cell; `--tag`/`--label` insert
  below the matched cell (must be unique)
- `wt remove-cell <name> --index N | --tag foo | --label foo`
  — delete matching cell(s); a tag may remove multiple (delete ranges from
  highest to lowest)
- `wt tag <name> --index N | --tag foo | --label foo [--add foo] [--remove bar]`
  — manage cell tags (unique match required)
- `wt clear-outputs <name> [--index N | --tag foo | --label foo | --from N]`
  — clear stored outputs of code cells (markdown cells skipped). `--from N`
  clears every code cell from index N to the end (handy for a trailing
  section like a problem set); with no locator, all code cells are cleared.
- `wt problem <course> <locator>` — print a problem statement (plus starter
  code) from the chapter notebooks. Locator forms: `7.3`, `07-3`, `07 3`,
  `07-projection-and-orthogonalization 3`, `projection 3`.
- `wt solution <course> <locator> [--raw]` — print a problem's decoded
  solution (worked text, answer, checks, reference code). `--raw` prints the
  stored ROT18-encoded cell source instead.
- `wt hint <course> <locator> [--level 1|2]` — progressive hint from the
  solution: level 1 = checks descriptions (no expected values) + first
  sentence of the worked text; level 2 = full worked text. Never the answer.
- `wt add-exercise <course> <chapter> --statement X [--starter X] --solution X
  [--number N]` — append a new problem + solution pair to a chapter. The
  statement is stored plaintext (tags `problem` + id); the solution is
  ROT18-encoded into a hidden code cell (tags `solution` + id, `#| echo:
  false` / `eval: false` / `output: false` header), so plaintext never reaches
  the notebook through this path. Number defaults to
  the next one in the chapter. This is the ONLY sanctioned way to add a new
  exercise, besides `wt solution-set` for updating an existing solution.
- `wt solution-set <course> <locator> --content X` — create or replace a
  problem's solution cell (encodes on write; plaintext in, encoded stored).
- `wt check <course>` — validate every chapter: problem cells are markdown and
  solution cells are hidden code cells, both with unique id tags matching
  `<chapter>-<n>`; each problem has a solution pair (and vice versa), solutions
  are wrapped and encoded. Exit 1 on any warning.
- `wt diff <name> [--base REF]` — markdown diff of a notebook vs a git ref
  (default HEAD): both sides rendered like `wt cat` (JSON-stripped, no
  outputs; solutions decoded), so the diff shows content, not `.ipynb` JSON.
- `wt run <name> [--index N] [--timeout S] [--kernel K]` — execute code cells
  in-place via nbclient, writing outputs back; exit code 1 if any cell errored.
  `--index N` runs only that cell in a fresh kernel (no state carries).
- `wt import <path.ipynb> notes|articles [<name>]` — import an external notebook
  (Colab/Kaggle) into a flat tier
- `wt import <path.ipynb> courses <course> [<chapter>] [--section <name>]`
  — import as a chapter of an existing course (copies into the course dir and
  registers in the course's sidebar)
- `wt render <tier> <name> | <path.ipynb>` — render notebook -> PDF
- `wt resume` — render `assets/resume.yaml` -> `assets/resume.tex` + `index.ipynb`
  via Jinja2 templates, then `pdflatex` -> `assets/resume.pdf` (builds in a
  temp dir). The YAML is the single source; edit it, never the generated
  `.tex`/`.ipynb`.
- `wt docs` — serve the site (blocking; :4200)
- `wt vault get|set|list|env <key>` — secret management