# Authoring Quarto articles

Official starting point: <https://quarto.org/docs/guide/>.

Use this reference for the document-level work of authoring a notebook-first article. Use [cell-options.md](cell-options.md) for executable-cell option syntax.

## Relevant Quarto topics

The Quarto guide's useful authoring routes are:

- [Markdown Basics](https://quarto.org/docs/authoring/markdown-basics.html): headings, links, lists, tables, equations, divs, spans, and callouts.
- [Figures](https://quarto.org/docs/authoring/figures.html) and [Tables](https://quarto.org/docs/authoring/tables.html): captions, sizing, accessibility, computations, and cross-references.
- [Diagrams](https://quarto.org/docs/authoring/diagrams.html): Mermaid and Graphviz diagrams.
- [Cross References](https://quarto.org/docs/authoring/cross-references.html): stable `fig-`, `tbl-`, `sec-`, and `eq-` labels with `@...` references.
- [Citations](https://quarto.org/docs/authoring/citations.html): bibliography metadata and citation syntax.
- [Article Layout](https://quarto.org/docs/authoring/article-layout.html): body, page, screen, and margin columns.
- [Using Python](https://quarto.org/docs/computations/python.html) and [Execution Options](https://quarto.org/docs/computations/execution-options.html): executable cells, output control, and rendering behavior.

Do not load every linked page for an ordinary edit. Follow the link that matches the current authoring problem.

## Syntax quick reference

These are the portable patterns most often needed in a notebook-first article. Use the linked Quarto pages for less common attributes and format-specific behavior.

### Markdown Basics

Use headings, links, images, lists, footnotes, code fences, and LaTeX math as ordinary Markdown:

```markdown
## A section

[Quarto](https://quarto.org/) is a publishing system.

![A useful caption](images/example.png){fig-alt="A concise description of the image."}

- First item
- Second item

Inline math is written as $E = mc^2$.

$$
\widehat{\theta} = \arg\max_\theta L(\theta; x)
$$
```

Leave a blank line before a list. Do not put blank lines inside a display-math block. Use Quarto divs for callouts:

```markdown
::: {.callout-note}
This is a useful observation.
:::
```

### Figures

For a static image, put the caption and figure attributes on the image:

```markdown
![A useful caption](images/example.png){#fig-example width=80% fig-alt="A concise description of the image."}
```

Use `fig-align="left"` when alignment matters. For a Python plotting cell, put `#| label: fig-example`, `#| fig-cap: "..."`, and optional `#| fig-alt: "..."` at the top of the cell; see [cell-options.md](cell-options.md). Refer to the result as `@fig-example`.

### Tables

Use pipe-table alignment markers for small hand-authored tables:

```markdown
| Model | Score |
|:------|------:|
| Baseline | 0.72 |
| MLE | 0.81 |
: **Results.** Validation scores. {#tbl-results}
```

Use `tbl-colwidths="[75,25]"` or classes such as `{.striped .hover}` when needed. For a Python-generated table, use `#| label: tbl-results` and `#| tbl-cap: "..."` on the producing cell, then emit Markdown with `display(Markdown(...))`; see [cell-options.md](cell-options.md). Refer to it as `@tbl-results`.

### Diagrams

Use a Mermaid fenced block for a simple flow diagram:

````markdown
```{mermaid}
flowchart LR
    A[Data] --> B[Estimator]
    B --> C[Estimate]
```
````

Use the [Diagrams](https://quarto.org/docs/authoring/diagrams.html) page when choosing between Mermaid, Graphviz, and other diagram types or when adding diagram-specific options.

### Citations

Declare a bibliography in the notebook's YAML front matter:

```yaml
bibliography: references.bib
# csl: nature.csl  # optional
```

Then use Pandoc citation syntax in Markdown:

```markdown
The estimator is consistent [@author2024].

[@author2024; @other2023]

[-@author2024] introduced the method.
```

Use page or chapter locators when needed, for example `[@author2024, pp. 33-35]`.

### Cross References

Labels must use a type prefix. Define labels on sections, figures, tables, and equations, then refer to them with `@...`:

```markdown
## Estimator {#sec-estimator}

![Sampling distribution](images/sampling.png){#fig-sampling}

$$
\widehat{\theta} = \arg\max_\theta L(\theta; x)
$$ {#eq-mle}

See @fig-sampling, @eq-mle, and @sec-estimator.
```

Use `#fig-...`, `#tbl-...`, `#sec-...`, and `#eq-...`, not untyped labels. Avoid underscores in labels because they can cause LaTeX cross-reference problems.

### Article Layout

Quarto articles have body, page, screen, and margin column concepts. Use layout divs sparingly and check the target format:

```markdown
::: {.column-body-outset}
This content extends beyond the normal body column.
:::

::: {.column-margin}
A short marginal note.
:::
```

HTML, PDF, and Typst do not implement every layout feature identically. Prefer normal body content unless a wider or marginal placement materially improves the article.

## Article workflow

1. **Establish metadata.** Put the title and other document metadata in the notebook's YAML front matter. In Watchtower, preserve the existing `date` and `categories` conventions.
2. **Build a readable argument.** Start with an introduction, define notation before using it, and organize the body with descriptive headings. Each section should advance the explanation rather than merely group code cells.
3. **Use Markdown as the default authoring language.** Prefer Markdown, Pandoc Markdown, LaTeX math, Quarto divs, callouts, and spans. Keep raw HTML or format-specific markup for cases where the portable primitives are insufficient.
4. **Pair prose with computation.** Precede each code cell with its purpose and follow it with interpretation. Split expensive computation from presentation-only plotting or table-formatting cells when that makes the rendered article easier to scan.
5. **Make outputs referenceable.** Give figures and tables stable type-prefixed labels and captions in the cell that produces them. Refer to them in prose with `@fig-name` or `@tbl-name`. Use equation and section labels when readers need to navigate back to a result.
6. **Make figures and tables legible.** Add informative captions and alternative text where appropriate, format numeric columns deliberately, and use layout or margin placement only when it improves the argument. Check the target output format because layout behavior can differ across HTML, PDF, and Typst.
7. **Add citations deliberately.** If the article cites external work, add the bibliography in front matter and use Quarto citation syntax. Keep citations near the claims they support; do not replace a citation with a bare URL when a bibliographic reference is appropriate.
8. **Render from the canonical source.** In Watchtower, notebook outputs are stored inline and Quarto renders without re-execution. Run the relevant cells explicitly, inspect their outputs, then run `wt docs` or the project render command.

## Compact patterns

### Figure and cross-reference

```python
#| label: fig-sample
#| fig-cap: "**Sample distribution.** The observed values and fitted density."
#| fig-alt: "Histogram of the sample with a fitted density curve."
```

Refer to it in prose as `@fig-sample`.

### Table and cross-reference

```python
#| label: tbl-results
#| tbl-cap: "**Results.** Validation metrics for each model."
```

Refer to it in prose as `@tbl-results`. For a table produced by Python, use the Markdown-output pattern in [cell-options.md](cell-options.md) and keep the caption on the table-producing cell when Quarto can associate it with that output.

### Equation and section labels

```markdown
## Estimator {#sec-estimator}

$$
\widehat{\theta} = \arg\max_\theta L(\theta; x)
$$ {#eq-mle}
```

Refer to these as `@sec-estimator` and `@eq-mle`.
