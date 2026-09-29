# Repository notation guide

This file defines repository-wide conventions for mathematical prose, equations,
dimensions, and the correspondence between notation and code. It is deliberately
domain-agnostic. Subject-specific conventions belong in the relevant course or
notebook and should be defined there when they are introduced.

## General principles

- Give each symbol one meaning within a section or derivation.
- Define every nonstandard symbol at first use, close to the equation or code
  that depends on it.
- State dimensions and indexing conventions when they affect an operation or
  interpretation.
- Prefer established mathematical notation, but prioritize consistency and
  explicit definitions over visual cleverness.
- Keep names for data, parameters, intermediate values, and outputs distinct.

## Typeface

- Use uppercase bold sans-serif for matrices and linear maps:
  `\textbf{\textsf{X}}` and `\textbf{\textsf{W}}`.
- Use lowercase bold sans-serif for individual vectors:
  `\textbf{\textsf{x}}` and `\textbf{\textsf{v}}`.
- Use ordinary italic math for scalars, dimensions, probabilities, and indices:
  `$n,d,p,i$`.
- Use upright roman operators with `\operatorname{...}` for named mathematical
  operations, such as `\operatorname{Softmax}` or `\operatorname{argmax}`.
- Use `\mathbb{R}` and similar blackboard-bold symbols for number systems and
  other standard mathematical sets.

## Shapes and indices

- Use `$\in\mathbb{R}^{m\times n}$` for a standalone shape declaration.
- Write matrix dimensions as rows by columns, and annotate a product when the
  intermediate shapes are important to the explanation:
  `$\underbrace{A}_{m\times n}\underbrace{B}_{n\times p}$`.
- Use `$^\top$` for transpose.
- State whether indices are zero-based or one-based when the distinction matters.
- Use different indices for different axes, and do not overload an index within
  one local derivation.
- Annotate the output shape of a product or function when it helps establish
  that the operation is valid or clarifies the result.

## Math-to-code correspondence

- Use lowercase `snake_case` for Python variables and keep code names close to
  the corresponding mathematical symbols.
- Make the distinction between parameters and computed values visible in names;
  do not reuse one identifier for both.
- Keep batch, sequence, feature, and other axes explicit in code when omitting
  them from textbook equations would make the correspondence ambiguous.
- Use library conventions for standard objects, and define any project-specific
  naming convention before relying on it across multiple examples.

## Domain-specific extensions

Add a subject-specific notation section to the relevant course or notebook when
needed. Extend this file only for conventions that are broadly reusable across
the repository; do not turn it into a glossary for one project, course, or model.
