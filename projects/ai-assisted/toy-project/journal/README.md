# Journal

Each file here records one step of the process. Steps are numbered and read in order.

## Step file template

Every step file uses this structure:

```
# Step NN: <title>

Status: Planned | In progress | Done
Git: <commit hash(es) once done>

## Goal
What this step achieves, in one or two sentences.

## Plan
The intended changes, files, and tests, written before any code.

## Approval
Who approved the plan, and any changes made to it during review.

## Changes
What was actually done. Note any deviation from the plan and why.

## Verification
Exact commands run and their results.

## Review
Findings from the independent review (observer or human), and how they were resolved.

## Drift check
Does the code still match ARCHITECTURE.md? Anything that needs a doc change?

## Lessons
What worked, what did not, and what to change in the process.
```

## Why the journal exists

Agent-generated code is quick to produce and hard to remember. The journal makes each
decision visible later, so the human can reconstruct the project's reasoning without
re-reading the whole codebase.
