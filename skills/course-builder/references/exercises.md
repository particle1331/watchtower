# Course exercises

Read this reference when adding, editing, or reviewing exercise prompts or
starter code in course chapters. Learner answers can be evaluated in context
when requested; a stored solution is not required for each prompt.

## Authoring

Place a `## Exercises` section after the chapter's summary or last teaching
section. Give each exercise a clear Markdown heading and a self-contained
statement. Include any data, assumptions, expected artifact, and checks the
learner needs to attempt it. Put optional starter code in the next code cell.

Use `wt cat <chapter> --context N` to inspect the surrounding cells. Add or
revise prompts with `wt insert-cell`, `wt append-cell`, and `wt edit-cell`; use
`wt tag` when a stable `problem` tag helps locate an exercise later. Re-read
indices after inserting or removing cells. Run edited starter code and inspect
its stored output. Review the notebook with `wt diff` and render the chapter.

For assessment, read the prompt, learner response, and relevant chapter or
project code, then evaluate the answer against the stated requirements. Give
specific feedback and checks. Do not generate a hidden answer cell by default.

## Existing solutions

Archived solutions are at
`archive/2026-09-30/nb/courses/solutions.qmd`. Archived chapter notebooks may
contain hidden, encoded solution cells; preserve them when reviewing source.
`wt cat` shows their stored source, while `wt diff` compares stored source.
