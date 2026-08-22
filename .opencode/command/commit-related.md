---
description: Group current worktree changes and commit them with conventional commit messages
agent: build
---

Review the current Git worktree and commit the user's related changes in coherent groups.

1. Inspect `git status --short`, the textual diff, and notebook changes through the repository's `.venv/bin/wt diff` wrapper. Do not read raw notebook JSON.
2. Infer groups from the actual intent of the changes. Keep unrelated changes in separate commits and preserve existing user work.
3. Run relevant checks before committing. For notebook edits, inspect changed cells and run affected code cells when practical. For Python or tooling changes, run `make lint` and `make typecheck` when applicable.
4. Stage only the files belonging to the current group and commit each group with the repository's bracketed convention: `type: [scope] description`, such as `feat: [skills] add shared notebook skill setup` or `docs: [content] improve weak supervision explanation`.
5. Never commit secrets, generated artifacts, or unrelated changes. Do not rewrite existing commits, reset the worktree, or discard changes.
6. After committing, verify `git status --short` and report the commit hashes, messages, checks run, and any remaining changes.
