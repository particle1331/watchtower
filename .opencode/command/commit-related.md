---
description: Quickly group and commit current worktree changes; use --session-only to limit commits to this conversation's edits
agent: build
---

Quickly review the current Git worktree and commit the user's related changes in coherent groups. Prefer decisive path-based grouping over exhaustive analysis.

Flags come from "$ARGUMENTS". Supported: `--session-only`, optionally with a value (`--session-only=true`, `--session-only false`). The bare flag means enabled; absent or a false-y value (`false`, `no`, `off`, `0`) means disabled. Unknown flags: ignore them and note that in the final report.

1. Start with `git status --short` and a concise `git diff --stat`/name list. Do not perform a repo-wide deep read before forming groups.
2. Group by obvious paths and shared intent first: a project with its matching course/docs, a standalone skill, and a lockfile with the dependency change it serves. Keep unrelated top-level paths separate. Use the smallest number of coherent groups that is obvious from the paths.
3. Inspect textual diffs only for each candidate group's risky or representative files. For notebooks, use the repository's `.venv/bin/wt diff` wrapper; never read raw notebook JSON. Do not inspect every notebook cell when the path and representative diff establish the intent.
4. Run only targeted, relevant checks after grouping. Skip expensive broad checks unless the changed project requires them. For Python, prefer the project's explicit test command and targeted compile/lint checks. Do not let a missing optional dependency block committing unrelated validated groups.
5. Human-in-the-loop: call the `question` tool immediately with one concise question if group ownership is ambiguous, a file appears to mix unrelated edits, a secret/generated artifact may be involved, a destructive action seems necessary, or more than roughly 10 focused inspection/tool calls or two inspection passes would be needed. Do not keep investigating just to avoid asking. If the grouping is obvious, do not ask for confirmation.
6. With `--session-only` enabled, restrict every group to files YOU created or modified during THIS conversation (your own edit/write calls, `wt run` output write-backs, files scaffolded by commands you ran this session). Determine this set from the conversation history, intersect it with `git status --short`, and treat all other dirty paths as out of scope: leave them unstaged and list them under "left untouched" in the final report. Do not attempt hunk-level splitting of a file that mixes session edits with pre-existing ones; either include the whole file in its group and say so, or leave it out. If no session changes can be identified, stop without committing and explain why. With the flag disabled, skip this step entirely.
7. Stage only the files belonging to the current group and commit each group with the repository's bracketed convention: `type [scope]: description`, such as `feat [skills]: add shared notebook skill setup` or `docs [content]: improve weak supervision explanation`.
8. Never commit secrets, generated artifacts, or unrelated changes. Do not rewrite existing commits, reset the worktree, or discard changes.
9. After committing, verify `git status --short` and report the commit hashes, messages, checks run, whether session-only mode was active, and any remaining changes.
