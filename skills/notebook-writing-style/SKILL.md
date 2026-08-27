---
name: notebook-writing-style
description: Prose and formatting conventions for watchtower notes, articles, and course chapters. Use when writing or editing any .ipynb content under nb/notes/, nb/articles/, or nb/courses/ — voice, emphasis, math, code-cell prose, callouts, tables, footnotes, and Quarto spans. Defer Quarto/Jupyter cell-option syntax to the quarto-jupyter skill. Use ONLY when working on notebook content, not tooling code under src/ or projects/.
---

# Notebook writing style

Conventions for the canonical content in `nb/notes/`, `nb/articles/`, and `nb/courses/`.
The watchtower source walk-through (`nb/notes/005-wt-src-walkthrough`) and the
Maximum Likelihood note (`nb/notes/006-maximum-likelihood-estimation`) are the
reference exemplars; consult them when the rules below need a concrete instance.
For a larger example, see the Weak Supervision article
(`nb/articles/003-weak-supervision`).

## Voice

- **Direct and declarative.** Prefer impersonal exposition for definitions and
  technical explanations. Use "you" when an outcome or instruction genuinely
  addresses the learner, and use "we" sparingly for a shared derivation. The
  voice should read naturally rather than reveal a mechanical pronoun rule.
- **Action-first.** Lead with the action, not the agent: "To implement X:
  (1) ... and (2) ..." over "X is implemented by ...." Describe what the code
  does, not what the author did.
- **Explanatory density.** Keep the motivation, mechanism, and consequence when
  they matter. Concision removes repetition; it does not remove concrete facts,
  reasoning, caveats, or useful transitions.
- **Interpret code and outputs.** Prose after a code block adds information:
  interpretation, a connection to theory, or a consequence. It does not merely
  paraphrase the code.
- **Specific claims over salesmanship.** Replace hype adjectives ("powerful,"
  "elegant," "seamless," "beautiful") with the concrete property being claimed.
- **Fully explained contrasts in prose.** Compressed forms such as "X changes; Y stays"
  or "Not X, but Y" are useful only when the surrounding prose names the
  concrete referents, mechanism, and caveats. Avoid slogan-like fragments that
  stand in for that explanation.
- **Concrete language in prose.** Prefer the literal noun ("the hosting platform,"
  "the implementation") to a metaphorical stand-in ("the substrate," "the
  machinery") when the metaphor makes the mechanism less precise.

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
- **Tables summarize; prose teaches.** Use inline enumeration when prose flows
  and tables when three or more items share the same attributes. Keep the
  surrounding rationale and causal links; do not turn an explanatory section
  or a meaningful "why it matters" comparison into status labels.
- **Preserve narrative continuity.** When revising existing course prose,
  retain accurate details, examples, rationale, transitions, cross-links, and
  teaching sequence. Correct stale claims in place instead of replacing a
  sound explanation with a terse summary.
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
