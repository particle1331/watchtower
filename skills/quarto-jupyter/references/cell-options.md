# Quarto Jupyter cell options

Official reference: <https://quarto.org/docs/reference/cells/cells-jupyter.html>

This is a focused reference for the options most likely to matter when editing a Quarto-rendered Python notebook.

## Figures and code

```python
#| label: fig-example
#| fig-cap: "A caption for the rendered figure."
#| code-fold: true
```

- `label` gives the cell a stable identifier, such as `fig-example` for a figure.
- `fig-cap` is the figure caption option. `cap` is not the Jupyter figure option.
- `code-fold: true` collapses the source in HTML while leaving the output visible.
- Put the label and caption on the cell that actually generates the figure.

For a table, use `tbl-cap` rather than `fig-cap`.

## Markdown and table output

For a Python object that should be stored as Markdown output:

```python
from IPython.display import Markdown, display

display(Markdown("| a | b |\n|---|---|\n| 1 | 2 |"))
```

For printed Markdown that Quarto should insert without an output container:

```python
#| output: asis
print("| a | b |\n|---|---|\n| 1 | 2 |")
```

Use one approach consistently for a given cell. `display(Markdown(...))` produces a Jupyter `text/markdown` display; `output: asis` treats printed output as raw Markdown.

## YAML quoting

Cell options are YAML. A double-quoted value interprets backslash escapes, so a caption containing LaTeX such as `$-\infty$` can fail with an unknown-escape error. Prefer a single-quoted YAML value when the caption contains LaTeX backslashes:

```python
#| fig-cap: '**Likelihood.** The curve reaches $-\infty$ outside the support.'
```

Alternatively, escape the backslash for a double-quoted YAML value.
