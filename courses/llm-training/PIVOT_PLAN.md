# LLM Training Course Migration Checklist

Status: active migration checklist  
Last updated: 2026-08-26

## Follow the migrated course guidance

The stable course promise and design now live in the learner-facing
[`index.ipynb`](index.ipynb) and
[`00-overview.ipynb`](00-overview.ipynb). Those pages have already been
migrated and are the source of truth for:

- the ProofLM thesis and the boundary around “from scratch”;
- the target model and checkpoint lineage;
- smoke, standard, CUDA, and optional MLX execution paths;
- corpus, tokenizer, generated-proof, and structural-split contracts;
- pretraining, posttraining, tool-use, and LoRA objectives;
- evaluation standards, acceptance gates, and non-goals; and
- the intended chapter-by-chapter artifact handoff.

Do not copy those specifications back into this file. Follow them while
migrating the implementation and chapter notebooks. If measurement or
implementation evidence forces a central design change, update Chapter 00
first and then adjust the affected migration tasks here.

This file tracks unfinished transition work only. Delete it after every task
is closed and the course can stand on its index, overview, chapters, project,
and frozen artifacts.

## Completed orientation work

- [x] Rewrite `index.ipynb` as the concise learner-facing course home.
- [x] Add `00-overview.ipynb` with the complete course architecture and
  evidence contract.
- [x] Register Chapter 00 before the numbered chapters in `_quarto.yml`.
- [x] Rename the Chapter 01 surface from general orientation to the corpus and
  data contract.
- [x] Align the sidebar labels with the target chapter arc.
- [x] Render the index, Chapter 00, and Chapter 01 successfully.
- [x] Confirm `wt check llm-training` passes after the orientation changes.

## Migration order

Work in artifact dependency order. Do not rewrite downstream notebooks around
interfaces that do not yet exist.

- [ ] Freeze the package, configuration, artifact, and evaluator schemas.
- [ ] Build and test the propositional proof engine and data fixtures.
- [ ] Build the tokenizer, decoder, and trainer.
- [ ] Produce and verify the complete CPU smoke lineage.
- [ ] Qualify the CUDA environment and produce the canonical base checkpoint.
- [ ] Migrate Chapters 01–07 around the shared data, model, trainer, and
  evaluator artifacts.
- [ ] Implement proof SFT, DPO, and verifier-guided RL before migrating
  Chapters 08–10.
- [ ] Implement the proof tools and LoRA path before migrating Chapters 11–12.
- [ ] Populate Chapters 13–14 from the frozen checkpoint family and reports.
- [ ] Add the CUDA reference and optional MLX appendix only after their shared
  contracts are stable.

## Phase 0: backing project and frozen contracts

- [ ] Scaffold `projects/proof-lm/` as a workspace project.
- [ ] Add the reusable `proof_lm` package and tests directory.
- [ ] Define named `smoke` and `standard` configurations without scattering
  device-specific constants through notebooks.
- [ ] Define the experiment-record schema shared by every training and
  evaluation stage.
- [ ] Define the checkpoint schema, including model, optimizer, scheduler,
  scaler, data cursor, RNG state, configuration, lineage, and cost metadata.
- [ ] Define tokenizer, dataset-manifest, evaluator-report, and tool-trace
  schemas.
- [ ] Define the project-owned gitignored artifact root and its cleanup rules.
- [ ] Commit only small fixtures, configurations, manifests, hashes, tests,
  and compact reports.
- [ ] Add tests that reject incompatible tokenizer, dataset, checkpoint, and
  evaluator identities.
- [ ] Benchmark one exact smoke workload locally before fixing practical
  timeout expectations.

Exit condition:

- [ ] One configuration can identify every input and output needed to
  reproduce a stage.

## Phase 1: proof engine, generated data, and Chapter 01

### Backing implementation

- [ ] Implement the formula AST, parser, renderer, and truth-table semantics.
- [ ] Implement the natural-deduction rules and independent proof verifier.
- [ ] Implement checked countermodel search.
- [ ] Generate positive examples from valid proof skeletons.
- [ ] Generate controlled invalid examples by perturbing proofs and goals.
- [ ] Add parse/render round-trip, generated-proof validity, countermodel, and
  assumption-discharge property tests.
- [ ] Implement structural split keys for theorem families, proof shapes,
  depths, variable families, paraphrases, perturbations, and tool schemas.
- [ ] Build the checked smoke corpus manifest consumed by later chapters.

### Chapter 01 migration

- [ ] Preserve the existing manifest, normalization, hashing, duplicate, and
  deliberate-contamination explanations.
- [ ] Replace fixture-only corpus claims with the mixed language,
  mathematics, and verifier-generated proof data contract.
- [ ] Add source revision, license, generator version, structural family, and
  token-budget fields to the manifest examples.
- [ ] Add a counter-example showing why random row splits leak renamed or
  cosmetically altered instances of the same theorem skeleton.
- [ ] Import the real package functions rather than duplicating their final
  implementation in notebook cells.
- [ ] Produce and inspect the stored smoke manifest and split-audit outputs.
- [ ] Update Chapter 01 exercises through the sanctioned exercise commands.

Exit condition:

- [ ] Every generated positive proof verifies, every attached countermodel is
  valid, and no structural split key crosses a boundary.

## Phase 2: tokenizer and decoder

### Chapter 02: tokenizer and batching

- [ ] Preserve the small character, byte, word, and toy-BPE examples as
  counter-examples that expose coverage and compression tradeoffs.
- [ ] Train the real byte-level BPE tokenizer from the checked corpus sample.
- [ ] Reserve and test every document, proof, role, tool, and turn-boundary
  token required by the course.
- [ ] Measure ordinary-text compression, formula fragmentation, proof length,
  fallback behavior, padding utilization, and context truncation.
- [ ] Serialize and hash the vocabulary, merges, normalizer, and special-token
  map.
- [ ] Implement the actual packed dataset, boundary policy, masks, and batches
  consumed by pretraining.
- [ ] Update exercises and store the tokenizer report.

### Chapter 03: PyTorch foundations and baselines

- [ ] Replace the parallel NumPy model path with PyTorch tensors and modules.
- [ ] Preserve the mathematical derivations of softmax and cross-entropy.
- [ ] Compare an elementary PyTorch reference loss with the reusable library
  function.
- [ ] Introduce broadcasting, indexing, parameters, autograd, optimizers,
  devices, and deterministic generators through the baselines.
- [ ] Keep one local gradient check using PyTorch tensors.
- [ ] Train the n-gram, bigram, and fixed-context MLP baselines on the smoke
  corpus.
- [ ] Freeze the baseline likelihood and proof-completion thresholds that
  ProofLM must beat.
- [ ] Update exercises and stored outputs.

### Chapter 04: trainable decoder and qualification

- [ ] Implement a short functional attention reference in elementary PyTorch.
- [ ] Implement the reusable embeddings, causal attention, RoPE, pre-norm
  blocks, GELU MLP, final norm, and tied language-model head.
- [ ] Implement autoregressive generation and serialization.
- [ ] Compare the functional attention reference with the reusable module.
- [ ] Assert shapes, exact parameter count, weight tying, finite gradients,
  save/load identity, and absence of future-token influence.
- [ ] Complete a tiny-batch overfit.
- [ ] Implement the CPU/CUDA canary for block outputs, logits, loss,
  gradients, one optimizer update, serialization, and resume behavior.
- [ ] Run the complete memory-qualification cycle and record the environment
  report before later CUDA stages are allowed.
- [ ] Update exercises and stored outputs.

Exit condition:

- [ ] The frozen tokenizer round-trips, the model passes every causal and
  serialization invariant, and the selected CUDA environment is qualified.

## Phase 3: trainer, base checkpoint, and shared evaluation

### Chapter 05: causal pretraining

- [ ] Implement next-token labels, padding and boundary loss masks, gradient
  accumulation, validation, sampling, and periodic evaluation.
- [ ] Save and restore every model, optimizer, scheduler, scaler, data-cursor,
  and RNG component.
- [ ] Prove exact interrupted-versus-uninterrupted equivalence for the smoke
  profile.
- [ ] Complete the local CPU smoke pretraining run and inspect its artifacts.
- [ ] Run the measured CUDA pilot before authorizing the standard run.
- [ ] Complete the canonical base-pretraining run with persistent checkpoints
  and verified resume.
- [ ] Store loss, source-level validation, samples, throughput, memory,
  environment, and cost reports.
- [ ] Freeze and hash the canonical base checkpoint.
- [ ] Update exercises and stored outputs.

### Chapter 06: optimization and systems

- [ ] Preserve the optimizer and schedule derivations while connecting each
  term to the real PyTorch trainer state.
- [ ] Remove parallel NumPy optimizer implementations from the core path.
- [ ] Inspect ProofLM parameter groups, warmup, cosine decay, gradient norms,
  clipping, accumulation, and precision behavior.
- [ ] Benchmark context length, microbatch size, and accumulation under a fixed
  token budget.
- [ ] Report sustained throughput, estimated FLOPs, peak memory, wall time,
  cost, and validation loss.
- [ ] Inject an interruption and demonstrate exact checkpoint recovery.
- [ ] Update exercises and stored outputs.

### Chapter 07: checkpoint evaluation

- [ ] Make every evaluator consume explicit checkpoint, tokenizer, dataset,
  decoding, seed, and evaluator identities.
- [ ] Add held-out likelihood by source, calibration, memorization canaries,
  overlap audits, and generation-diversity reports.
- [ ] Add mathematical syntax, theorem completion, proof-prefix completion,
  verifier validity, pass-at-k, proof length, and countermodel checks.
- [ ] Freeze general-language, mathematical-language, proof, shifted-proof,
  and retention suites.
- [ ] Store compact reports that downstream chapters reuse without changing
  prompts or evaluator versions.
- [ ] Update exercises and stored outputs.

Exit condition:

- [ ] The smoke lineage is exactly reproducible, the canonical base checkpoint
  beats the frozen baselines, and all shared evaluator reports are versioned.

## Phase 4: proof posttraining

### Chapter 08: proof supervised fine-tuning

- [ ] Serialize theorem requests, proof objects, countermodels, clarification
  requests, and correction turns.
- [ ] Derive response masks from message-span metadata.
- [ ] Fine-tune the canonical base checkpoint and record its parent.
- [ ] Compare full-sequence and response-only loss under matched token budgets.
- [ ] Evaluate held-out structures, paraphrases, renamed variables,
  alternative proofs, invalid goals, pass-at-k, and language retention.
- [ ] Add a qualitative error table keyed by verifier error code.
- [ ] Freeze the proof-SFT checkpoint and update exercises and outputs.

### Chapter 09: DPO

- [ ] Construct checked preference pairs covering validity, discharge,
  citations, formatting, repair, and countermodels.
- [ ] Compute sequence log-probabilities from response-token masks for the
  policy and frozen reference.
- [ ] Train from the proof-SFT checkpoint and record the branch lineage.
- [ ] Report preference accuracy, KL, proof validity, proof length, and
  retention.
- [ ] Preserve the length-shortcut lesson with intentionally confounded and
  length-matched controls.
- [ ] Freeze the DPO report and update exercises and outputs.

### Chapter 10: verifier-guided reinforcement learning

- [ ] Sample multiple proof completions per held-out theorem prompt.
- [ ] Parse and score them with the versioned verifier.
- [ ] Implement the simple group-normalized sequence-level update before any
  optional PPO extension.
- [ ] Track KL, entropy, validity, pass-at-k, proof length, exploit rate, and
  retention.
- [ ] Run a deliberately weak-verifier branch and compare proxy reward with
  the independent verifier.
- [ ] Freeze the RL report and update exercises and outputs.

Exit condition:

- [ ] At least one posttraining branch improves independent proof validity on
  structurally held-out theorems without crossing the retention threshold.

## Phase 5: proof tools and matched adaptation

### Chapter 11: proof-tool environment

- [ ] Implement the typed proof-tool schemas, deterministic registry,
  execution loop, structured errors, and maximum-step protocol.
- [ ] Replace unrelated example tools with the declared proof tools.
- [ ] Generate call, no-call, multi-tool, malformed-result, and repair traces.
- [ ] Train the tool-calling branch from the frozen proof-SFT parent.
- [ ] Add the non-learning router baseline.
- [ ] Evaluate tool choice, arguments, schema validity, unnecessary calls,
  result use, repair, episode completion, paraphrases, and held-out schemas.
- [ ] Freeze the tool report and update exercises and outputs.

### Chapter 12: LoRA versus full fine-tuning

- [ ] Implement named LoRA injection with zero-impact initialization and
  frozen-base assertions.
- [ ] Implement adapter-only state dictionaries, merge, unmerge, and exact
  base restoration.
- [ ] Start the full and LoRA tool branches from the same parent checkpoint.
- [ ] Match ordered traces, response masks, tokens, updates, decoding, and
  evaluator versions.
- [ ] Report trainable parameters, optimizer memory, checkpoint size, wall
  time, proof and tool metrics, retention, and merge equivalence.
- [ ] Sweep rank only after the canonical rank-8 comparison is complete.
- [ ] Freeze the comparison report and update exercises and outputs.

Exit condition:

- [ ] Tool calling beats the router baseline on held-out requests, handles
  no-call cases, repairs some rejected proofs, and has a matched full-versus-
  LoRA comparison.

## Phase 6: reliability and capstone

### Chapter 13: measured failure modes

- [ ] Turn template leakage, theorem-skeleton leakage, variable renaming,
  depth, irrelevant premises, formatting, weak-verifier exploitation,
  unnecessary calls, ignored errors, and failed correction into executable
  suites.
- [ ] Compare the base, proof-SFT, DPO, RL, full-tool, and LoRA checkpoints.
- [ ] Populate the reliability taxonomy with real examples and effect sizes.
- [ ] Use behavioral localization before adding an activation probe or patching
  experiment.
- [ ] Include an unrelated-behavior control for any internal intervention.
- [ ] Update exercises and stored outputs.

### Chapter 14: end-to-end study

- [ ] Provide one command and configuration path that rebuilds all smoke
  artifacts.
- [ ] Provide one manifest that identifies every standard artifact.
- [ ] Compare the base, proof-SFT, DPO, RL, full-tool, LoRA-tool, and
  non-learning baselines under frozen prompts and evaluators.
- [ ] Run multiple seeds for affordable posttraining branches.
- [ ] Report means, dispersion, lineage, cost, proof validity, pass-at-k, tool
  correctness, repair, retention, exploit controls, failures, and limitations.
- [ ] Verify that another implementer can inspect the evaluator and reproduce
  comparable smoke results.
- [ ] Update capstone exercises and stored outputs.

Exit condition:

- [ ] The capstone scorecard is assembled entirely from frozen lineage
  artifacts and declared final evaluations rather than implicit retraining.

## Appendices

### CUDA reference

- [ ] Consolidate the CUDA concepts already introduced in Chapters 04–13.
- [ ] Document environment capture, CPU/CUDA parity, device placement,
  autocast, synchronization, memory counters, qualification gates, profiling,
  checkpoint transfer, storage, cost projection, and cleanup.
- [ ] Ensure the appendix is a reference, not the learner's first CUDA run.

### Optional MLX smoke comparison

- [ ] Implement the smoke model, loss, accumulation, validation, generation,
  checkpoint, and logging path in MLX.
- [ ] Import identical initial weights and ordered smoke batches.
- [ ] Compare float32 logits, loss, and gradients within declared tolerances.
- [ ] Complete the bounded smoke run without crossing the process-memory or
  swap gates declared in Chapter 00.
- [ ] Report compilation, synchronization, throughput, memory pressure, swap,
  wall time, and the training curve.
- [ ] Label the comparison as an end-to-end system comparison and keep it out
  of the canonical PyTorch lineage.

## Per-notebook migration procedure

Apply this checklist to every chapter transition:

- [ ] Locate the relevant cells with `wt find`.
- [ ] Read each cell with context using `wt cat --context`.
- [ ] Preserve correct derivations, examples, rationale, transitions, and
  exercises that still serve the target artifact.
- [ ] Move reusable computation into `projects/proof-lm/` and import it from
  the notebook.
- [ ] Mutate notebook cells only through the `wt` cell commands.
- [ ] Add new exercises only with `wt add-exercise`.
- [ ] Update existing solutions only with `wt solution-edit`.
- [ ] Re-execute every edited code cell and inspect its stored outputs.
- [ ] Review the notebook with `wt diff`.
- [ ] Run `wt check llm-training` after exercise work.
- [ ] Render the affected notebook and inspect figures, tables, equations,
  Mermaid diagrams, and internal links.
- [ ] Confirm the chapter's artifact and report match the handoff promised in
  Chapter 00.

## Migration completion

- [ ] Every chapter imports the cumulative package instead of maintaining a
  parallel notebook-only implementation.
- [ ] Every heavy chapter has a complete CPU smoke path and a qualified,
  budgeted standard path where required.
- [ ] Every result carries the artifact and evaluator identity required by
  Chapter 00.
- [ ] Every sidebar label matches its final chapter title and artifact.
- [ ] All modified code cells have current stored outputs.
- [ ] `wt check llm-training` passes.
- [ ] The complete course renders without execution or broken links.
- [ ] Another implementer can reproduce the smoke lineage and inspect the
  standard lineage from committed manifests and reports.
- [ ] Remove this migration checklist.
