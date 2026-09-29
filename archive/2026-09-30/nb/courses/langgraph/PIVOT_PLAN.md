# LangGraph Course Pivot Plan

Status: core migration complete; scoped follow-ups remain  
Last updated: 2026-08-27

## Follow the migrated course guidance

The stable target course promise and technical contract live in the
learner-facing [`index.ipynb`](index.ipynb) and
[`00-overview.ipynb`](00-overview.ipynb). Those pages are the source of truth
for the Change Planner artifact, its search and memory boundaries, execution
profiles, evaluation standard, and chapter handoffs.

This file records the completed core migration and its scoped follow-ups. Do
not copy the full target architecture into this checklist. If implementation
evidence forces a course-wide design change, update Chapter 00 first and then
adjust the tasks below. Keep this file as the migration record while the
follow-ups remain useful.

## Pivot decision

The previous running project was a Philippine legal-research workflow. Its
workflow mechanics were useful, but validating its domain conclusions required
legal expertise that is unrelated to the intended learning goals.

The new running project is a **Change Planner Agent with LangGraph**. Given a
bounded change request and a versioned repository snapshot, it searches code,
tests, configuration, documentation, and Git history; relates the retrieved
evidence; analyzes plausible regressions; and produces a cited, reviewable
change plan. The agent is *introspective* in the practical sense that it
investigates the system's own artifacts and prior investigations instead of
conducting open-ended general research.

## Migration guardrails

- Keep the canonical agent read-only. It may run explicitly allowed tests, but
  it does not edit code, merge changes, or deploy systems.
- Keep ingestion, indexing, retrieval, reranking, symbol analysis, Git
  inspection, test discovery, citation checks, and metrics in deterministic
  project modules. LangGraph owns stateful orchestration around those modules.
- Attach every evidence item and durable memory to a repository identity,
  revision, recoverable source location, and content fingerprint.
- Treat checkpoints and long-term memory as different contracts. Checkpoints
  resume an investigation; memory selectively carries validated experience
  into later investigations.
- Compare lexical, dense, hybrid, graph-enhanced, agentic, and memory-augmented
  variants against explicit baselines before claiming an improvement.
- Use pinned fixture repositories and seeded changes for canonical evaluation.
  Real-repository runs are integration demonstrations, not the answer key.
- Build the replacement in a new `projects/change-planner/` workspace member.
  Preserve `projects/evidence-brief-agent/` until the replacement covers the
  course contracts and its removal is separately reviewed.

## Orientation work

- [x] Record the pivot and migration order in this checklist.
- [x] Rewrite `index.ipynb` as the concise learner-facing home for the Change
  Planner course.
- [x] Rewrite `00-overview.ipynb` with the complete search, evidence, memory,
  graph, and evaluation contracts.
- [x] Align chapter labels and filenames in `_quarto.yml` after the target
  chapter surfaces are ready.
- [x] Render the index and Chapter 00 and inspect the resulting pages.

## Migration order

Work in artifact dependency order. Do not rewrite downstream notebooks around
interfaces that have not been frozen in the backing project.

- [x] Freeze the request, repository snapshot, evidence, hypothesis, test-link,
  memory, plan artifact, and evaluation schemas.
- [x] Freeze the fixture repositories, seeded change scenarios, gold evidence
  sets, affected-test sets, and split policy.
- [x] Scaffold `projects/change-planner/` and implement the deterministic
  ingestion, retrieval, code-intelligence, and evaluation interfaces.
- [x] Establish lexical and dense baselines before adding hybrid fusion,
  reranking, graph traversal, or agentic query refinement.
- [x] Implement the LangGraph workflow only after the plain search and staged
  planning baselines are measurable.
- [x] Implement checkpointing and revision-aware memory after evidence identity
  and invalidation rules are stable.
- [x] Migrate Chapters 01 through 08 in dependency order, then rebuild the
  capstone and rename its file.
- [x] Remove the legal-research terminology, fixtures, links, and sidebar labels
  only after their replacements are present and rendered.

## Phase 0: target contracts and fixtures

- [x] Define `ChangeRequest`, including repository identity, target revision,
  requested outcome, scope, constraints, and execution policy.
- [x] Define immutable `RepositorySnapshot` identity from repository, commit,
  index configuration, and content fingerprints.
- [x] Define evidence records for code, symbols, tests, configuration,
  documentation, diffs, and history with recoverable locations.
- [x] Define regression hypotheses with supporting, refuting, missing, and
  verification evidence.
- [x] Define the Markdown change plan and machine-readable investigation record.
- [x] Create a pinned Python fixture repository catalog with architecture questions,
  planned changes, seeded regressions, known affected surfaces, and executable
  tests.
- [x] Separate worked, validation, and held-back challenge scenarios by change
  family rather than by random query rows.

Exit condition:

- [x] A fixture scenario identifies the expected evidence, affected behavior,
  related tests, regression, and acceptable unknowns without model judgment.

## Phase 1: search and retrieval foundation

- [x] Implement repository ingestion with language, path, symbol, test,
  configuration, documentation, revision, and fingerprint metadata.
- [x] Implement literal retrieval as the first measurable baseline.
- [x] Implement deterministic dense retrieval with a pinned fixture contract.
- [x] Implement hybrid fusion and reranking without hiding component scores.
- [x] Report recall at k, reciprocal rank, nDCG, evidence precision, latency,
  and index cost by retriever variant.
- [x] Add index freshness checks and explicit stale-index failure behavior.

Exit condition:

- [x] Hybrid retrieval is compared with its additional cost on the frozen
  validation set, and the course reports the tradeoff rather than assuming an
  improvement.

## Phase 2: code, test, and history relations

- [x] Extract symbols, definitions, references, imports, and configuration
  relationships for the supported Python-first scope.
- [x] Link tests to symbols and behaviors using names, imports, and source
  metadata; coverage and co-change evidence remain future extensions.
- [x] Retrieve commits and diffs by affected path, symbol, behavior, and test.
- [x] Build a versioned evidence graph without treating graph proximity as
  proof of behavioral impact.
- [x] Evaluate affected-file, affected-symbol, and related-test recall.

Exit condition:

- [x] Every reported relationship is recoverable to repository evidence, and
  the agent distinguishes a candidate relation from a verified one.

## Phase 3: LangGraph investigation workflow

- [x] Compare a direct search pipeline and staged Python planner with the graph
  workflow on the same scenarios.
- [x] Implement typed investigation state with reducers only for legitimate
  parallel contributions.
- [x] Use conditional routing for simple answers, missing evidence, stale
  indexes, exhausted budgets, and verification failures.
- [x] Use `Send` for accountable parallel investigation branches and validate
  every scheduled result at the join.
- [x] Use `Command` where a node must update state and choose the next route.
- [x] Stream search, hypothesis, verification, and plan events without exposing
  private model reasoning.

Exit condition:

- [x] The graph adds observable branching, recovery, parallelism, or
  resumability that the simpler baselines do not provide.

## Phase 4: verification, review, and durability

- [x] Implement targeted test selection and explicitly authorized execution.
- [x] Record test command identity, environment, result, and output fingerprint
  as evidence without treating a passing test as complete proof.
- [x] Add a human review interrupt that can approve, edit, reject, or request
  more evidence.
- [x] Add a SQLite-backed restart demonstration; replay and fork remain scoped
  extensions of the same checkpoint contract.
- [x] Make test execution, export, and other effects idempotent across resume.

Exit condition:

- [x] A restarted investigation resumes without duplicating completed searches,
  test executions, or exports.

## Phase 5: revision-aware agent memory

- [x] Separate working state from typed episodic, semantic, and procedural
  memory records; the first implementation focuses on episodic admission.
- [x] Define initial admission, retrieval, invalidation, and deletion policies;
  consolidation and semantic promotion remain scoped extensions.
- [x] Revalidate memories against the target revision and changed source
  fingerprints before using them as current evidence.
- [x] Preserve provenance from a memory back to the investigation and source
  evidence that created it.
- [x] Evaluate repeated investigations with no memory, valid memory, irrelevant
  memory, conflicting memory, and stale memory.

Exit condition:

- [x] The memory scorecard demonstrates valid reuse and freshness/conflict
  boundaries without introducing stale hits in the frozen scenarios.

Follow-up: add learned admission/consolidation policies and a quality threshold
for unsupported-claim rates before treating memory as a production feature.

## Phase 6: chapter migration

- [x] Chapter 01: replace the legal task boundary with search pipeline versus
  graph-worthy change investigation.
- [x] Chapter 02: replace `BriefState` with typed change-investigation state and
  bounded evidence cycles.
- [x] Chapter 03: teach lexical, dense, hybrid, bounded agentic, symbol, test,
  and history retrieval with versioned evidence.
- [x] Chapter 04: route ambiguity, missing evidence, stale indexes, tool faults,
  and exhausted verification budgets.
- [x] Chapter 05: fan out code, test, configuration, documentation, and history
  branches, then validate the join.
- [x] Chapter 06: review and revise a change plan through interrupts.
- [x] Chapter 07: separate investigation checkpoints from revision-aware
  long-term memory.
- [x] Chapter 08: evaluate retrieval, impact analysis, regression localization,
  memory, workflow behavior, latency, and cost.
- [x] Chapter 09: integrate and publish the Change Planner capstone.

## Final acceptance and cleanup

- [x] The capstone answers codebase questions and plans changes from versioned,
  recoverable evidence.
- [x] It relates implementation surfaces to tests and distinguishes retrieved,
  inferred, and verified relationships.
- [x] It identifies seeded regression risks and proposes targeted verification
  while preserving unknowns.
- [x] It demonstrates checkpoint resume and revision-aware memory without stale
  claims or duplicate effects.
- [x] Retrieval and bounded agentic variants, plus memory/no-memory workflow
  variants, are compared with fixed metrics and frozen evaluation identities.
- [x] The final artifact includes current behavior, proposed changes, affected
  surfaces, regression hypotheses, test plan, rollout considerations, rollback
  considerations, observability checks, evidence, and unresolved questions.
- [x] `wt check langgraph`, relevant project tests, notebook execution, and site
  rendering pass.
- [x] Retain `projects/evidence-brief-agent/` as an explicitly preserved legacy
  project; the active course and sidebar no longer depend on it.
- [x] Retain this checklist as the migration record. Its scoped follow-ups are
  learned memory admission/consolidation and checkpoint fork demonstrations.
