---
description: Check your answer to a course problem against the stored solution
agent: build
---

The user wants to check their answer to a course problem against the stored solution.

1. Resolve the course:
   - If `$1` matches a directory under `courses/` (e.g. `cla`, `mlops`), that is the course and the remaining arguments locate the problem.
   - Otherwise infer the course from context: which course notebook the user is currently working in, or the most recently discussed course. If the course is still ambiguous, ask the user which course before proceeding.
2. Resolve the problem. Accept any of these forms:
   - `/check-answer cla 7.3 <answer>` — `$1` is the course, `$2` is `chapter.problem` (e.g. `7.3` = problem 3 of chapter 7)
   - `/check-answer cla 07 3 <answer>` — `$2` is the chapter (number, stem like `07-projection-and-orthogonalization`, or fuzzy title match), `$3` is the problem number
   - `/check-answer cla 07-3 <answer>` — `$2` is a full problem id
   The user's answer is everything in `$ARGUMENTS` after the locator arguments. If it is empty, ask the user to paste their answer (text, math, or code) and stop — do not reveal the solution yet.
3. Fetch the problem statement with `.venv/bin/wt problem <course> <locator>` (statements are plaintext in the notebooks). Fetch the decoded solution with `.venv/bin/wt solution <course> <locator>`. Do NOT read `.ipynb` files directly, and never reveal the encoded source — the CLI decodes it for you.
4. Grade, don't dump:
   - If the solution has `**Checks:**` (numeric expected values): extract the user's numeric answer(s) and compare against `expected ... ± tolerance`. State pass/fail per check.
   - If the user's answer is code: run it and compare its output against the checks.
   - For theory problems: compare the user's reasoning against the `**Solution.**` text and judge correctness, noting missing or wrong steps.
5. Report: a verdict per part, what is right, what is wrong, and the reference answer (`**Answer:**` / `**Solution.**`). Only reveal the full worked solution after grading the user's answer.
