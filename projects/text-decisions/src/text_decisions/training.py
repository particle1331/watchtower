"""Visible training loop and small CLI for the course's decision-model lab."""

import argparse
import json
import random
from pathlib import Path
from typing import Any

import torch
from huggingface_hub import hf_hub_download
from torch import nn
from transformers import (
    AutoModel,
    AutoTokenizer,
    ModernBertConfig,
    ModernBertModel,
    PreTrainedTokenizerFast,
    Qwen2Config,
    Qwen2Model,
)

from .model import (
    DecisionModel,
    candidate_texts,
    decision_loss,
    joint_text,
    questions_from,
    typed_outputs,
)


def read_records(path: Path) -> list[dict[str, Any]]:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    records = [json.loads(line, object_pairs_hook=unique_pairs) for line in path.read_text().splitlines() if line.strip()]
    if not records:
        raise ValueError("empty dataset")
    for record in records:
        questions_from(record)
        if not record.get("group_id") or not record.get("task_id"):
            raise ValueError("task_id and group_id are required split metadata")
    return records


def check_splits(train: list[dict[str, Any]], validation: list[dict[str, Any]]) -> None:
    train_groups = {r["group_id"] for r in train}
    validation_groups = {r["group_id"] for r in validation}
    if train_groups & validation_groups:
        raise ValueError("a source group appears in both training and validation")


def shuffled_record(record: dict[str, Any], rng: random.Random) -> dict[str, Any]:
    """Targets are keyed by semantic label, so permutation preserves supervision."""
    result = {**record, "questions": {}}
    for name, spec in record["questions"].items():
        pairs = list(spec["criteria"].items())
        rng.shuffle(pairs)
        result["questions"][name] = {**spec, "criteria": dict(pairs)}
    return result


def tiny_backbone(family: str, records: list[dict[str, Any]]) -> tuple[Any, Any, str]:
    """Offline architectural smoke check, with a locally fitted word tokenizer."""
    from tokenizers import Tokenizer, models, pre_tokenizers, trainers

    backend = Tokenizer(models.WordLevel(unk_token="[UNK]"))
    backend.pre_tokenizer = pre_tokenizers.Whitespace()
    corpus = []
    for record in records:
        questions = questions_from(record)
        corpus.extend(candidate_texts(record["state"], questions))
        corpus.append(joint_text(record["state"], questions)[0])
    backend.train_from_iterator(corpus, trainers.WordLevelTrainer(special_tokens=["[PAD]", "[UNK]", "[EOS]"]))
    tokenizer = PreTrainedTokenizerFast(tokenizer_object=backend, pad_token="[PAD]", unk_token="[UNK]", eos_token="[EOS]")
    common: dict[str, Any] = dict(vocab_size=len(tokenizer), hidden_size=32, intermediate_size=64,
                  num_hidden_layers=2, num_attention_heads=4, pad_token_id=0, bos_token_id=2, eos_token_id=2)
    if family == "qwen2":
        config = Qwen2Config(**common, num_key_value_heads=2, max_position_embeddings=512, use_cache=False)
        config._attn_implementation = "eager"
        return Qwen2Model(config), tokenizer, "last"
    config = ModernBertConfig(**common, cls_token_id=2, sep_token_id=2, max_position_embeddings=512, local_attention=128,
                             attention_dropout=0.0, embedding_dropout=0.0, mlp_dropout=0.0)
    config._attn_implementation = "eager"
    return ModernBertModel(config), tokenizer, "mean"


def load_backbone(checkpoint: str, revision: str | None = None) -> tuple[Any, Any, str]:
    # Resolve mutable branch names once, then load tokenizer and weights at that commit.
    config_path = Path(hf_hub_download(checkpoint, "config.json", revision=revision))
    resolved = config_path.parent.name
    tokenizer = AutoTokenizer.from_pretrained(checkpoint, revision=resolved, trust_remote_code=False, use_fast=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    backbone = AutoModel.from_pretrained(checkpoint, revision=resolved, dtype=torch.float32,
                                         attn_implementation="eager", trust_remote_code=False)
    backbone.config._commit_hash = resolved
    if backbone.config.model_type not in {"qwen2", "modernbert"}:
        raise ValueError("this teaching lab supports Qwen2/2.5 and ModernBERT")
    if hasattr(backbone.config, "use_cache"):
        backbone.config.use_cache = False
    return backbone, tokenizer, "last" if backbone.config.model_type == "qwen2" else "mean"


def adapt_backbone(backbone: Any, method: str) -> Any:
    if method == "lora":
        from peft import LoraConfig, get_peft_model

        # ModernBERT uses a fused QKV projection; Qwen exposes separate projections.
        targets = ["q_proj", "v_proj"] if backbone.config.model_type == "qwen2" else ["Wqkv"]
        return get_peft_model(backbone, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.0, target_modules=targets))
    backbone.requires_grad_(method == "full")
    return backbone


def make_optimizer(model: DecisionModel, backbone_lr: float, head_lr: float) -> torch.optim.AdamW:
    groups = [{"params": [p for p in model.head.parameters() if p.requires_grad], "lr": head_lr}]
    trainable_backbone = [p for p in model.backbone.parameters() if p.requires_grad]
    if trainable_backbone:
        groups.append({"params": trainable_backbone, "lr": backbone_lr})
    return torch.optim.AdamW(groups, weight_decay=0.0)


def train_step(model: DecisionModel, tokenizer: Any, records: list[dict[str, Any]],
               optimizer: torch.optim.Optimizer, max_length: int = 512) -> float:
    model.train()
    if not any(p.requires_grad for p in model.backbone.parameters()):
        model.backbone.eval()
    optimizer.zero_grad(set_to_none=True)
    total = 0.0
    # Gradient accumulation gives each record equal weight, then averages its questions.
    for record in records:
        logits = model(record, tokenizer, max_length)
        loss = decision_loss(logits, record)
        if not torch.isfinite(loss):
            raise ValueError("non-finite loss")
        (loss / len(records)).backward()
        total += float(loss.detach()) / len(records)
    nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
    optimizer.step()
    return total


@torch.no_grad()
def evaluate(model: DecisionModel, tokenizer: Any, records: list[dict[str, Any]], max_length: int = 512) -> dict[str, float]:
    model.eval()
    loss = correct = count = 0.0
    for record in records:
        logits = model(record, tokenizer, max_length)
        loss += float(decision_loss(logits, record))
        for scores, q in zip(logits, questions_from(record), strict=True):
            answer = record["answers"][q.name]
            if "label" in answer:
                correct += int(q.labels[int(scores.argmax())] == answer["label"])
                count += 1
    return {"loss": loss / len(records), "accuracy": correct / count if count else 0.0}


def save_model(model: DecisionModel, tokenizer: Any, directory: Path, metadata: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    if hasattr(model.backbone, "peft_config"):
        # This lab never resizes/trains embedding weights during projection-only LoRA.
        model.backbone.save_pretrained(directory / "backbone", save_embedding_layers=False)
    else:
        model.backbone.save_pretrained(directory / "backbone")
    tokenizer.save_pretrained(directory / "tokenizer")
    torch.save(model.head.state_dict(), directory / "head.pt")
    metadata = {**metadata, "head": model.head_name, "pooling": model.pooling, "width": model.width}
    (directory / "run.json").write_text(json.dumps(metadata, indent=2) + "\n")


def load_model(directory: Path, device: str = "cpu") -> tuple[DecisionModel, Any, dict[str, Any]]:
    metadata = json.loads((directory / "run.json").read_text())
    if (directory / "backbone/adapter_config.json").exists():
        from peft import PeftModel

        base, _, _ = load_backbone(metadata["checkpoint"], metadata["revision"])
        backbone = PeftModel.from_pretrained(base, directory / "backbone")
    else:
        backbone = AutoModel.from_pretrained(directory / "backbone", attn_implementation="eager")
    tokenizer = AutoTokenizer.from_pretrained(directory / "tokenizer", use_fast=True)
    model = DecisionModel(backbone, metadata["head"], metadata["pooling"], metadata["width"])
    model.head.load_state_dict(torch.load(directory / "head.pt", map_location="cpu", weights_only=True))
    return model.to(device).eval(), tokenizer, metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--checkpoint", required=True)
    train.add_argument("--revision")
    train.add_argument("--head", choices=["candidate", "joint"], default="candidate")
    train.add_argument("--adaptation", choices=["full", "lora"], default="lora")
    train.add_argument("--train", type=Path, required=True)
    train.add_argument("--validation", type=Path, required=True)
    train.add_argument("--output", type=Path, required=True)
    train.add_argument("--epochs", type=int, default=2)
    train.add_argument("--warmup-epochs", type=int, default=1)
    train.add_argument("--batch-size", type=int, default=2)
    train.add_argument("--backbone-lr", type=float, default=2e-5)
    train.add_argument("--head-lr", type=float, default=1e-3)
    train.add_argument("--max-length", type=int, default=512)
    train.add_argument("--seed", type=int, default=7)
    train.add_argument("--device", default="cpu")
    infer = sub.add_parser("predict")
    infer.add_argument("--model", type=Path, required=True)
    infer.add_argument("--request", type=Path, required=True)
    infer.add_argument("--device", default="cpu")
    args = parser.parse_args()
    if args.command == "predict":
        model, tokenizer, metadata = load_model(args.model, args.device)
        record = json.loads(args.request.read_text())
        with torch.no_grad():
            print(json.dumps(typed_outputs(model(record, tokenizer, metadata["max_length"]), record), indent=2))
        return
    if args.epochs < 1 or args.warmup_epochs < 0 or args.batch_size < 1 or args.max_length < 1:
        parser.error("epochs, batch size and max length must be positive; warmup may be zero")
    if args.output.exists():
        parser.error("choose a new output directory so a previous run is preserved")
    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    records, validation = read_records(args.train), read_records(args.validation)
    check_splits(records, validation)
    if args.checkpoint.startswith("tiny-"):
        if args.checkpoint not in {"tiny-qwen", "tiny-modernbert"}:
            parser.error("unknown tiny checkpoint")
        if args.adaptation != "full":
            parser.error("tiny smoke checkpoints use full adaptation")
        family = "qwen2" if args.checkpoint == "tiny-qwen" else "modernbert"
        backbone, tokenizer, pooling = tiny_backbone(family, records)
        resolved_revision = None
    else:
        backbone, tokenizer, pooling = load_backbone(args.checkpoint, args.revision)
        resolved_revision = getattr(backbone.config, "_commit_hash", args.revision)
    model = DecisionModel(backbone, args.head, pooling).to(args.device)
    metadata = {"checkpoint": args.checkpoint, "revision": resolved_revision, "max_length": args.max_length,
                "adaptation": args.adaptation, "seed": args.seed, "batch_size": args.batch_size,
                "warmup_epochs": args.warmup_epochs, "epochs": args.epochs,
                "backbone_lr": args.backbone_lr, "head_lr": args.head_lr,
                "train_groups": sorted({r["group_id"] for r in records}),
                "validation_groups": sorted({r["group_id"] for r in validation})}
    # Stage 1 checks a new head while the pretrained backbone is frozen.
    model.backbone.requires_grad_(False)
    optimizer = make_optimizer(model, args.backbone_lr, args.head_lr)
    for _ in range(args.warmup_epochs):
        train_step(model, tokenizer, records, optimizer, args.max_length)
    # Rebuild the optimizer when its set of trainable parameters changes.
    model.backbone = adapt_backbone(model.backbone, args.adaptation)
    optimizer = make_optimizer(model, args.backbone_lr, args.head_lr)
    best_loss = float("inf")
    for epoch in range(args.epochs):
        order = rng.sample(records, len(records))
        losses = []
        for start in range(0, len(order), args.batch_size):
            batch = [shuffled_record(r, rng) for r in order[start:start + args.batch_size]]
            losses.append(train_step(model, tokenizer, batch, optimizer, args.max_length))
        metrics = evaluate(model, tokenizer, validation, args.max_length)
        print(json.dumps({"epoch": epoch + 1, "training_loss": sum(losses) / len(losses), "validation": metrics}), flush=True)
        if metrics["loss"] < best_loss:
            best_loss = metrics["loss"]
            save_model(model, tokenizer, args.output, {**metadata, "best_epoch": epoch + 1, "validation": metrics})


if __name__ == "__main__":
    main()
