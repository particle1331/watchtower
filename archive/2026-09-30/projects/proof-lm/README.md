# ProofLM

Backing project for the Watchtower course [Training Language Models from
Scratch: From Pretraining to Proof Tools](../../nb/courses/llm-training/index.html).

The package owns the reusable implementation and the notebooks own the
derivations, experiments, and interpretation. The migration keeps a compact
CPU-smoke implementation here and leaves scale- and hardware-dependent claims
to explicitly qualified runs:

- `configs/smoke.yaml` is the local CPU profile, with a roughly 5M-parameter
  model and a 2M-token budget.
- `configs/standard.yaml` is the qualified CUDA profile, with the target
  roughly 54M-parameter model and 1B-token budget.
- Each profile names its input identities, device, artifact root, and output
  namespace, so a run can be reconstructed without notebook-local constants.
- `proof_lm.schemas` defines versioned configuration, experiment, tokenizer,
  dataset, checkpoint, evaluator-report, and tool-trace records.
- `proof_lm.logic` owns the formula AST, parser, renderer, truth-table
  semantics, natural-deduction verifier, checked countermodels, and generated
  positive/negative proof fixtures.
- `proof_lm.data` owns canonical text hashes, structural split assignment, the
  mixed language/mathematics/proof smoke corpus, and dataset-manifest rows
  consumed by Chapter 01.
- `proof_lm.tokenization` trains and verifies the serialized byte-level BPE
  artifact consumed by Chapter 02 and later model stages.
- `proof_lm.data.batching` owns packed next-token windows, EOS boundary loss
  masks, padding validity, and fixed-width batch grouping.
- `proof_lm.model` owns the small decoder-only PyTorch model with causal
  attention, RoPE, tied embeddings, generation, and masked loss.
- `proof_lm.trainer` owns ordered smoke updates plus model/optimizer/data/RNG
  checkpoint state and exact resume support.
- `proof_lm.evaluation` and `proof_lm.optimization` own masked likelihood,
  proof-verifier metrics, schedules, gradient clipping, and parameter groups.
- `proof_lm.posttraining` owns role-derived SFT masks, DPO margins, group
  advantages, and verifier rewards; `proof_lm.tools` owns typed deterministic
  proof tools; `proof_lm.lora` owns adapter injection and reversible merging.
- `proof_lm.schemas.validate_evaluation_bundle` rejects reports that combine
  incompatible checkpoint, tokenizer, dataset, or evaluator identities.
- `artifacts/` is project-owned and gitignored. Only small fixtures,
  configurations, manifests, hashes, tests, and compact reports belong in Git.

Run the Phase 0 contract tests from this directory with:

```bash
uv run pytest
```

The package entry point runs the fixed schema/identity workload used to measure
the contract layer locally:

```bash
uv run proof-lm
```

That benchmark is not a model-training throughput claim. The Chapter 05 smoke
lineage and checkpoint are now stored under `artifacts/checkpoints/smoke/`; a
measured standard-scale throughput and hardware qualification remain separate
gates.
