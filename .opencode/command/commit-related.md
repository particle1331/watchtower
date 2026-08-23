---
description: Group current worktree changes and commit them with conventional commit messages; pass --session-only to commit only this conversation's edits
agent: build
---

Review the current Git worktree and commit the user's related changes in coherent groups.

Flags come from "$ARGUMENTS". Supported: `--session-only`, optionally with a value (`--session-only=true`, `--session-only false`). The bare flag means enabled; absent or a false-y value (`false`, `no`, `off`, `0`) means disabled. Unknown flags: ignore them and note that in the final report.

1. Inspect `git status --short`, the textual diff, and notebook changes through the repository's `.venv/bin/wt diff` wrapper. Do not read raw notebook JSON.
2. Infer groups from the actual intent of the changes. Keep unrelated changes in separate commits and preserve existing user work.
3. Run relevant checks before committing. For notebook edits, inspect changed cells and run affected code cells when practical. For Python or tooling changes, run `make lint` and `make typecheck` when applicable.
4. With `--session-only` enabled, restrict every group to files YOU created or modified during THIS conversation (your own edit/write calls, `wt run` output write-backs, files scaffolded by commands you ran this session). Determine this set from the conversation history, intersect it with `git status --short`, and treat all other dirty paths as out of scope: leave them unstaged and list them under "left untouched" in the final report. Do not attempt hunk-level splitting of a file that mixes session edits with pre-existing ones; either include the whole file in its group and say so, or leave it out. If no session changes can be identified, stop without committing and explain why. With the flag disabled, skip this step entirely.
5. Stage only the files belonging to the current group and commit each group with the repository's bracketed convention: `type [scope]: description`, such as `feat [skills]: add shared notebook skill setup` or `docs [content]: improve weak supervision explanation`.
6. Never commit secrets, generated artifacts, or unrelated changes. Do not rewrite existing commits, reset the worktree, or discard changes.
7. After committing, verify `git status --short` and report the commit hashes, messages, checks run, whether session-only mode was active, and any remaining changes.
