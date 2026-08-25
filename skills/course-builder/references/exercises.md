# Course problems and solutions

Read this reference before adding, editing, removing, or reviewing course
problems, starter code, solutions, or hints.

## Identity and layout

Exercise identity is stored in Jupyter tags; pairing is by shared id, never by
position.

- A problem statement is a Markdown cell tagged `problem` and `<chapter>-<n>`,
  for example `07-3`.
- Its heading is `### [P<NN>.<N>] Title`, where `NN` is the chapter number and
  `N` is the problem number.
- Optional starter code immediately follows the statement.
- The solution is a code cell tagged `solution` and the same id, directly after
  the statement or starter.

The solution starts with:

```text
#| echo: false
#| eval: false
#| output: false
```

Its body is stored with ROT18 obfuscation: letters shifted by 13, digits by 5,
and every non-empty line prefixed with `# `. This is a spoiler guard, not
security. Blank lines remain blank.

## Sanctioned commands

- Add an exercise only with
  `wt add-exercise <course> <chapter> --statement X [--starter X] --solution X`.
  It assigns the next number and encodes the solution before writing.
- Update or create an existing solution only with
  `wt solution-edit <course> <locator> --content X`.
- Read a decoded solution with `wt solution <course> <locator>` or
  `wt cat <path> --tag <id> --decode`.
- Read progressive hints with `wt hint <course> <locator> --level 1|2`.
  Level 1 returns check descriptions without expected values plus the first
  sentence of the worked text; level 2 returns the full worked text. Neither
  level reveals the answer.
- Remove exercise cells through the `wt` cell commands, highest index first,
  while preserving pair integrity.

Never write a plaintext solution with `edit-cell`, `insert-cell`, or direct
notebook manipulation. Never hand-encode a new exercise when the sanctioned
commands can enforce the invariant. To revise an existing solution, read it
decoded and write the revised plaintext back through `wt solution-edit`.

Locators such as `7.3`, `07-3`, `07 3`, and `<chapter-stem> 3` resolve to the
same pair.

## Verification

After any problem or solution change:

1. Run `wt check <course>` and resolve every warning; exit code 1 must be fixed
   before completion.
2. Read the problem and decoded solution together.
3. Execute starter code when applicable.
4. Confirm the pair remains consecutive: problem, optional starter, solution.
5. Review the notebook with `wt diff` and render the affected chapter.
