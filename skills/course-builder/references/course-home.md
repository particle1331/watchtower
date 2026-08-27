# Course home and Chapter 00

Read this reference only when creating or revising `index.ipynb`,
`00-overview.ipynb`, the course promise, the learning path, or the whole-course
technical contract. Once those pages are stable, ordinary chapter work should
read the pages themselves rather than reload this authoring guidance.

## Index page: the course README

The `index.ipynb` is the learner-facing home page. It should be concise but
substantive: a learner should understand the promise, scope, path,
prerequisites, and expected outcome in one sitting.

1. **Frontmatter:** `title`, `description`, `categories`, and optional `image`
   such as `"./img/<course>-cover.png"`. Quarto renders the title as the page
   H1, so the body must not repeat an H1.
2. **Short introduction:** one or two paragraphs explaining what the course is
   and who it is for, ending with the governing idea stated once as a bolded
   label in the form `**Design rule:** ...`.
3. **Completed-course outcome:** name the artifact, capability, proof, or
   comparison the learner will finish with. State scope boundaries when the
   title could otherwise overpromise.
4. **Learning path:** use a table with one row per chapter and a one-line
   description of what it teaches or adds. Group rows by the same phases or
   parts used in the sidebar.
5. **Prerequisites:** separate tooling from assumed knowledge.
6. **Execution at a glance:** name the default local path and any paid,
   remote, optional, or accelerated path without reproducing the full setup or
   resource-qualification procedure.
7. **Important notes:** link a backing project when one exists and explain its
   relationship to the notebooks. Add rigid notation or other before-starting
   conventions here.

Use only stable, learner-relevant decisions on the index. Detailed
architecture, artifact lineage, hardware and cost estimates, data-source
contracts, evaluation gates, equations, and serialization examples belong in
Chapter 00 when they are important to understanding the course. Migration
history, authoring status, and rewrite instructions belong in neither page.

Do not create a sibling `README.md`; `index.ipynb` is the course README.

## When to add Chapter 00

Add `00-overview.ipynb` when the course follows one artifact through several
stages, branches into matched comparisons, has distinct execution profiles, or
depends on a nontrivial data and evaluation contract. A compact or mostly
linear course should begin directly with Chapter 01.

Chapter 00 is a learner-facing conceptual reference, not an implementation
plan. It explains the complete course deeply enough that later chapters can
refer back to a shared design. Write for a reader who satisfies the stated
prerequisites but has not learned the course-specific vocabulary or
implementation. By the end, that reader should be able to describe the major
objects, transformations, comparisons, and success criteria at a surface
level, while later chapters retain the complete derivations and builds.

Include the sections that matter for the course:

- the running project and governing thesis;
- the precise scope boundary and what the course owns versus what libraries or
  platforms supply;
- what the completed course must demonstrate;
- the target system or artifact, including its components and lineage;
- the relationship between local/smoke and substantial/standard execution
  paths, including honest resource expectations;
- the data or input contract and evaluation standard;
- the chapter-by-chapter build, naming the artifact or evidence contributed by
  each stage; and
- the acceptance conditions and non-goals that bound the final claims.

## Technical altitude

Write Chapter 00 as explanatory course prose rather than a checklist. Use a
lineage or architecture diagram when it clarifies the whole build, tables for
repeated comparisons, and the real technical objects that organize the
course. Introduce representative equations, code snippets, configuration,
schemas, or serialization examples when they reveal mechanisms or interfaces
that later chapters will develop.

Keep this preview accessible at the prerequisite level:

- Define every course-specific term and mathematical symbol at first use.
- Introduce an equation with the question it answers, then interpret its terms
  and practical consequence in prose.
- Introduce code with its role in the complete system, then explain the
  invariant or interface it exposes.
- Use genuine course equations and APIs while leaving complete derivations,
  implementation details, and exercises to the relevant chapter.
- Connect each technical preview to the chapter that makes it operational.
- Distinguish planning estimates from values learners will measure.

## Content routing test

| Reader question | Location |
|---|---|
| Should I take this course, what will I build, and where do I start? | `index.ipynb` |
| How does the complete system fit together, and what counts as success? | `00-overview.ipynb` |
| How do I derive, implement, test, and interpret this stage? | The relevant numbered chapter |

The canonical example is the pair
`courses/llm-training/index.ipynb` and
`courses/llm-training/00-overview.ipynb`. Consult it for the division between
course-home orientation and technical overview, and for the expected technical
altitude. Reuse the pattern, not its language-model-specific contents.

## Verification

- Read both pages together and remove duplicated explanations.
- Check every chapter link and align the learning-path labels with the sidebar.
- Render both pages and inspect frontmatter, equations, diagrams, tables, code
  fences, and internal links.
