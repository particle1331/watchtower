---
name: quarto-jupyter
description: Author, edit, and review Quarto-rendered Jupyter notebooks and notebook-first articles, especially article structure, cell options, figures, tables, Markdown outputs, and preview failures.
---

# Quarto Jupyter notebooks

Use this skill when working on `.ipynb` files whose outputs are rendered by Quarto, including notebook-first articles. It is for Jupyter notebooks, not generic Quarto or knitr documents.

When authoring article content, read [references/article-authoring.md](references/article-authoring.md). When editing executable-cell options, read [references/cell-options.md](references/cell-options.md). Keep these concerns separate: the article reference governs document structure and reader-facing content, while the cell reference governs `#|` syntax and stored code outputs.

## Workflow

1. Read the repository's local agent instructions and use its notebook wrapper for notebook content. In Watchtower, use `.venv/bin/wt` and never edit raw `.ipynb` JSON.
2. Inspect the target cell and nearby cells before editing. Keep computation and presentation separate when a presentation cell only plots, prints, or formats results.
3. For article edits, follow [references/article-authoring.md](references/article-authoring.md) and preserve the notebook's existing narrative style.
4. Use the exact Jupyter cell-option names in [references/cell-options.md](references/cell-options.md). Do not invent aliases based on other Quarto engines.
5. Re-execute edited code cells with the notebook's prior state available, so stored outputs match the source. In Watchtower, use `wt run <name> --index N`.
6. Run the relevant Quarto preview or render after option changes. In Watchtower, use `wt docs`; if the sandbox blocks Quarto from listening on its preview port, retry through the approved elevated execution path.

## Cell-option rules

- Use `#| label: fig-name` and `#| fig-cap: "..."` for computational figures. Use `#| tbl-cap: "..."` for tables.
- Use `#| code-fold: true` when plotting or formatting code should be collapsed in HTML. Keep the figure or table output visible.
- For a real Markdown display from Python, use `IPython.display.Markdown` and `display`. For a string printed as raw Markdown, use `#| output: asis` and `print`.
- Treat cell-option values as YAML. LaTeX backslashes such as `\infty` must be in a YAML-safe single-quoted value or be escaped inside a double-quoted value.
- Preserve stable labels and captions when splitting a cell. Put the figure label/caption on the cell that actually produces the figure.
- For Mermaid diagrams in Markdown cells, use the Quarto fence ```` ```{mermaid} ```` with curly braces. A bare ```` ```mermaid ```` fence can be parsed inconsistently by the Jupyter-to-Quarto pipeline and cause rendering failures; keep the diagram source in the Markdown cell and validate it with a preview or render.

## Validation

After changing code or cell options:

- Inspect the source with `wt cat` and confirm the option names and cell types.
- Run the edited cell and inspect stored outputs with `wt output` or `wt cat --with-outputs`.
- Run `wt docs` or the project-equivalent Quarto build and resolve YAML, execution, and rendering errors before handing off.

Do not copy the entire Quarto manual into this skill. Consult the focused reference and the linked official documentation when an option is outside this skill's scope.
