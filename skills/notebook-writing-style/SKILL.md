---
name: notebook-writing-style
description: Prose and formatting conventions for watchtower notes, articles, and course chapters. Use when writing or editing any .ipynb content under notes/, articles/, or courses/ — voice, emphasis, math, code-cell prose, callouts, tables, footnotes, and Quarto spans. Defer Quarto/Jupyter cell-option syntax to the quarto-jupyter skill. Use ONLY when working on notebook content, not tooling code under src/ or projects/.
---

# Notebook writing style

Conventions for the canonical content in `notes/`, `articles/`, and `courses/`.
The watchtower source walk-through (`notes/005-wt-src-walkthrough`) and the
Maximum Likelihood note (`notes/006-maximum-likelihood-estimation`) are the reference
exemplars; consult them when the rules below need a concrete instance. For an example
of a larger article see the Weak Supervision article (articles/weak-supervision) as a
good example.

## Voice

- **Impersonal, declarative.** No "you," "the reader," or "your" as the default
  voice. Minimal "we" — at most once in a tight logical aside ("we obtain,"
  "we write"). Prefer "Recall," "Observe," "Notice," "It turns out."
- **Action-first.** Lead with the action, not the agent: "To implement X:
  (1) ... and (2) ..." over "X is implemented by ...." Describe what the code
  does, not what the author did.
- **No restating code.** The sentence after a code block adds new information
  — interpretation, connection to theory, a consequence. It never paraphrases
  the code the reader just saw.

## Emphasis

| Mark | Use for | Example |
|------|---------|---------|
| **Bold** | Key technical term at first definition; structural labels (`**The model.**`, `**NOTE:`); words central to the argument | **maximum likelihood estimation** |
| *Italics* | Informally-named terms; contrastive stress | the *naive* approach |
| `` `backticks` `` | Code tokens only — never for emphasis | `edit_cell` |
| `[term]{.mark}` | Quarto yellow highlight for a term being introduced | `[likelihood function]{.mark}` |
| `[term]{.underline}` | Quarto underline for contrastive stress | `[unbiased]{.underline}` |

## Structure

- **Counter-example before correct approach.** When teaching a method that
  supersedes a simpler one, present the simpler one first, expose its flaw,
  then introduce the correct approach. The contrast is the lesson.
- **Tables over bullets** for parallel comparative content. Use inline
  enumeration ("(1) ..., (2) ..., (3) ...") when prose flows; switch to a
  table when three or more items share the same attributes.
- **Every code cell preceded by descriptive markdown.** A bold structural
  label or a short terse intro — never an orphan code cell.
- **Post-code commentary** connects the output to the theory. It never
  restates the code.

## Math

- Inline LaTeX for quantities: $\mathbb{E}[X] = \theta/2$.
- Display equations for derivations; use `aligned` for multi-line steps.
- Box final results: `$$\boxed{\hat{\theta}_{\text{MLE}} = \max(x_i)}$$`.
- Shape annotations: `\underbrace{X}_{n \times d}` for matrix dimensions.
- Define notation inline at first use; do not front-load a notation table.
- Quarto cross-references: `{#eq-label}` on the equation, `@eq-label` in prose.

## Code cells

- **Numbered annotations** `# <1>`, `# <2>` for non-obvious lines. Explain
  each annotation in the *following* markdown cell, not in an inline comment.
- **Figure captions** open with a bold title phrase, then narrative:
  `**Synthetic sample.** Fifty draws from ...`. For the exact Quarto/Jupyter
  option name and placement, follow the `quarto-jupyter` skill.

## Quarto cell options

Cell-option syntax is a rendering concern rather than a prose convention. When
editing Jupyter notebooks rendered by Quarto, use the `quarto-jupyter` skill for
figure and table captions, code folding, Markdown output, YAML quoting, and
preview validation. This skill governs the writing around those cells, not the
`#|` option vocabulary.

## Callouts and footnotes

- **Callouts** (`:::{.callout-note}`, `:::{.callout-tip}`) for asides that
  would break the main flow: practical advice, warnings, alternative approaches.
- **Footnotes** `[^id]` only for: etymology, precise math qualifications,
  implementation alternatives, complexity heuristics. Never for main content.

## Links

- Wikipedia for named mathematical objects (distributions, theorems, algorithms).
- Library docs for API objects (PyTorch, NumPy, Quarto).
- Internal Quarto links for cross-note references: `<folder>/<filename>.html`.
