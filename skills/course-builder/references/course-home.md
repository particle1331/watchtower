# Course home and Chapter 00

Read this reference when creating or revising the CMS course home,
`00-overview.ipynb`, the course promise, learning path, or whole-course technical
contract. Ordinary chapter work should read the current content first.

## Course YAML and the CMS home

`backend/data/courses/<slug>.yaml` stores the initial writing brief, ordered TOC,
public chapter summaries, and committed `home` fields. The writing brief applies
only while Planned. Start consumes it and seeds the home once; later home edits
never synchronize back to historical plans. Read `wt context course/<slug>` for
current content and use CMS, CLI, or API supported mutations.

The CMS Course home tab edits these learner-facing sections in order:

1. **Course outcome** — contract `home.outcome`: concrete capabilities
   and the completed artifact, proof or comparison.
2. **Course description** — `home.description`: explain the purpose, intended
   audience, scope and what to expect. Keep internal design rules and execution
   notes in Internal notes.
3. **Related topics** — catalog `relations`: selected registered stable IDs,
   projected as links only when the target is eligible for the current site mode.
   Omit the generated section when no related links are eligible.
4. **Course content** — generated from the ordered TOC, chapter full titles and
   public summaries. Never maintain another chapter table in prose.
5. **Prerequisites** — the CMS has separate item lists:
   `home.requirements` for hardware, software, accounts, data or access needed
   to participate, and `home.prerequisites` for assumed knowledge and skills.
   Each non-empty list is combined into one enumeration in that order. Omit the
   generated section when both lists are empty. Keep detailed resource
   qualification in Chapter 00 when needed.
6. **References** — `home.references`, one outside source per item. Render these
   as an enumeration and omit the section when the list is empty.

The CMS list fields use one item per line; Markdown links work inside references.
Markdown is supported in prose fields. Inner headings render beneath these fixed
sections. Keep the home concise enough to read in one sitting. The public card
description is catalog `description`, set with `wt update --summary`; it remains
separate from the home description. Cover images and lifecycle remain Page metadata.

There is no editable `index.ipynb` or sibling README for a CMS course home. The
build generates the same public home URL from these fields. Legacy homes convert
through `wt migrate --course-homes`: review first, then apply with the returned
revision. Exact original notebooks and metadata are archived. Executable or
attachment-backed material must be explicitly moved to chapters before conversion.

Use `wt update course/<slug> --patch-file .tmp/home.json` with a payload such as
`{"contract":{"home":{"description":"Revised course prose."}}}`. Partial patches
preserve other home fields; pass the revision from `wt context` or `wt data`.
Notes and structured To-dos contain localized unfinished work and stay off the
site. Linked Kanban cards carry task-specific execution context. Commit accepted
course-level findings to the home and chapter-level findings to their notebook.

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
| Should I take this course, what will I build, and where do I start? | CMS course home |
| How does the complete system fit together, and what counts as success? | `00-overview.ipynb` |
| How do I derive, implement, test, and interpret this stage? | The relevant numbered chapter |

The archived pair at
`archive/2026-09-30/nb/courses/llm-training/index.ipynb` and
`archive/2026-09-30/nb/courses/llm-training/00-overview.ipynb` illustrates the
division between home and technical overview. It predates `course.yaml`; use
the pattern as source material, not as an active contract.

## Verification

- Read both pages together and remove duplicated explanations.
- Check every chapter link and align the learning-path labels with the sidebar.
- Render both pages and inspect frontmatter, equations, diagrams, tables, code
  fences, and internal links.
