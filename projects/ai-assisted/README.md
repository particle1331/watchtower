# AI-Assisted Development: A Process That Scales

This repository documents a repeatable process for building software with AI coding
agents **without losing architectural control** as a project grows.

It contains two things:

| Path | What it is |
|------|------------|
| [`WHITEPAPER.md`](WHITEPAPER.md) | The process, its rationale, and how to adopt it. *(written last, once the case study exists)* |
| [`toy-project/`](toy-project/) | A small Habit Tracker CLI, built step by step using the process. Every step is logged in `toy-project/journal/`. |

## How to read this repo

1. Read `WHITEPAPER.md` for the process.
2. Browse `toy-project/journal/` in order to see the process applied, step by step,
   including the mistakes and corrections.
3. Read `toy-project/ARCHITECTURE.md` and `toy-project/AGENTS.md` to see what the
   agent is given as ground truth.

## Git history as evidence

Each journal step is one or more commits. `git log --oneline` is the timeline of the
project, and each commit message references its journal entry.
