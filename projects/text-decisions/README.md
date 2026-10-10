# PyTorch text decision models

This is the runnable companion to Chapter 06 of **Build Text Classifiers from
Scratch**. It fine-tunes a Qwen2/2.5 or ModernBERT backbone with a shared
candidate scorer or a small joint attention head. Both return Choice, Noul and
Score distributions. The implementation uses PyTorch, Transformers and PEFT;
Unsloth and AnyJev are reading references, not runtime dependencies.

From the repository root:

```bash
uv sync --all-packages
uv run --package text-decisions text-decisions train \
  --checkpoint tiny-qwen --head joint --adaptation full \
  --train projects/text-decisions/examples/train.jsonl \
  --validation projects/text-decisions/examples/validation.jsonl \
  --epochs 2 --output .tmp/tiny-qwen-decision
uv run --package text-decisions text-decisions predict \
  --model .tmp/tiny-qwen-decision \
  --request projects/text-decisions/examples/request.json
```

The tiny checkpoint is a random two-layer transformer with a locally fitted
word tokenizer. It runs offline on CPU and checks the mechanics. The six
hand-authored training records and four validation records are fixtures, not
benchmark datasets. They cover sentiment and topic, include all three decision
types, and have disjoint source groups. Fixture accuracy is not evidence of
transfer or classifier quality.

For actual pretrained LLM adaptation:

```bash
uv run --package text-decisions text-decisions train \
  --checkpoint Qwen/Qwen2.5-0.5B --head joint --adaptation lora \
  --train projects/text-decisions/examples/train.jsonl \
  --validation projects/text-decisions/examples/validation.jsonl \
  --device cuda --epochs 2 --output .tmp/qwen-decision
```

This downloads the public pretrained checkpoint and tokenizer, warms up the
new head with frozen backbone weights, then trains the head and LoRA adapters.
The default is float32 eager attention for readability; `--device cpu` also
works with sufficient memory and time. For a real experiment, replace the
fixtures with audited task data, pin `--revision` to a checkpoint commit, and
reserve separate calibration/test partitions and an entirely held-out task.
Start with short inputs and small batches. Measure resources on your hardware.

Use `--checkpoint answerdotai/ModernBERT-base --adaptation full` for the encoder
comparison. LoRA is also supported: Qwen targets `q_proj` and `v_proj`, while
ModernBERT targets its fused `Wqkv`. `--head candidate` repeats the backbone
input per option; `--head joint` makes one backbone pass per record. The
per-record joint head prioritizes readable variable-size schemas. Training
accumulates gradients over records to implement the requested batch size.

Each JSONL row contains `task_id`, `group_id`, `state`, a `questions` dictionary,
and a separate `answers` dictionary. Inspect the included fixtures for the
complete schema. Answers never enter serialization. Criteria keys are semantic
labels; shuffling criteria preserves label-based targets. Noul has `false` and
`true` criteria; Score uses labels `0` through `K-1`. An answer can contain a
hard `label` or a `probabilities` dictionary over every allowed label. The
latter supports audited soft targets or teacher distributions.

The optimizer minimizes the mean question loss inside each record and then
the mean over records. Validation loss selects the saved checkpoint. The
saved directory contains tokenizer, backbone or adapters, head weights and
run metadata including the resolved backbone revision. It is an inference
artifact; optimizer state for resuming a run is not saved. Existing output
directories are rejected when starting a new run. Oversized inputs are rejected
so the caller must explicitly chunk or shorten the state while preserving its
question schema. Calibration and task-transfer evaluation are Chapter 07 and
capstone work, not hidden behavior in this small trainer.

Test the implementation:

```bash
PYTHONPATH=projects/text-decisions/src .venv/bin/pytest projects/text-decisions/tests
```

AnyJev's current `Decider` obtains probabilities by restricting a causal LM's
next-token logits to answer-label tokens, and corrects ordering/label biases
without updating weights. Its Tacit models are described as self-distilled;
the reviewed checkout supplies serving and evaluation, not a training script.
`restricted_label_loss` demonstrates a supervised extension of that readout;
it is not a reproduction of Tacit's training. The course derives this option
and the custom-head path directly on the page.
