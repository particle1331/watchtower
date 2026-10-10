"""Behavior checks for masking, semantic targets, adaptation and saved predictions."""

import copy
import random

import pytest
import torch
from text_decisions.model import DecisionModel, decision_loss, readout, typed_outputs
from text_decisions.training import (
    adapt_backbone,
    check_splits,
    load_model,
    make_optimizer,
    save_model,
    shuffled_record,
    tiny_backbone,
    train_step,
)


@pytest.fixture
def record():
    return {"task_id": "sentiment", "group_id": "review-1", "state": "A wonderful movie.", "questions": {
        "mood": {"type": "choice", "instructions": "What is the sentiment?", "criteria": {"negative": "unfavorable", "positive": "favorable"}},
        "liked": {"type": "noul", "instructions": "Did the reviewer like the movie?", "criteria": {"false": "no", "true": "yes"}},
        "rating": {"type": "score", "instructions": "Rate the sentiment.", "criteria": {"0": "negative", "1": "neutral", "2": "positive"}},
    }, "answers": {"mood": {"label": "positive"}, "liked": {"label": "true"}, "rating": {"label": "2"}}}


def test_readout_handles_left_and_right_padding():
    hidden = torch.arange(24, dtype=torch.float32).reshape(2, 4, 3)
    mask = torch.tensor([[0, 0, 1, 1], [1, 1, 0, 0]])
    assert torch.equal(readout(hidden, mask, "last"), torch.stack([hidden[0, 3], hidden[1, 1]]))
    assert torch.equal(readout(hidden, mask, "mean"), torch.stack([hidden[0, 2:].mean(0), hidden[1, :2].mean(0)]))


@pytest.mark.parametrize("family", ["qwen2", "modernbert"])
@pytest.mark.parametrize("head", ["candidate", "joint"])
def test_adaptation_and_reload(record, family, head, tmp_path):
    torch.manual_seed(7)
    backbone, tokenizer, pooling = tiny_backbone(family, [record])
    model = DecisionModel(backbone, head, pooling)
    # Warm-up must leave the backbone byte-identical.
    model.backbone.requires_grad_(False)
    frozen = {name: p.detach().clone() for name, p in model.backbone.named_parameters()}
    train_step(model, tokenizer, [record], make_optimizer(model, 1e-3, 1e-2))
    assert all(torch.equal(frozen[name], p) for name, p in model.backbone.named_parameters())
    model.backbone = adapt_backbone(model.backbone, "full")
    before = {name: p.detach().clone() for name, p in model.backbone.named_parameters()}
    head_before = {name: p.detach().clone() for name, p in model.head.named_parameters()}
    loss = train_step(model, tokenizer, [record], make_optimizer(model, 1e-3, 1e-2))
    assert loss > 0
    assert any(not torch.equal(before[name], p) for name, p in model.backbone.named_parameters())
    assert any(not torch.equal(head_before[name], p) for name, p in model.head.named_parameters())
    assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)
    model.eval()
    expected = model(record, tokenizer)
    response = typed_outputs(expected, record)
    assert all(abs(sum(item["probabilities"].values()) - 1) < 1e-6 for item in response.values())
    assert response["liked"]["true_probability"] == response["liked"]["probabilities"]["true"]
    assert 0 <= response["rating"]["expected_level"] <= 2
    save_model(model, tokenizer, tmp_path, {"checkpoint": "tiny", "revision": None, "max_length": 512})
    reloaded, reloaded_tokenizer, _ = load_model(tmp_path)
    actual = reloaded(record, reloaded_tokenizer)
    for a, b in zip(expected, actual, strict=True):
        assert torch.allclose(a, b, atol=1e-6)


@pytest.mark.parametrize("family", ["qwen2", "modernbert"])
def test_lora_changes_an_adapter(record, family):
    backbone, tokenizer, pooling = tiny_backbone(family, [record])
    backbone = adapt_backbone(backbone, "lora")
    model = DecisionModel(backbone, "candidate", pooling)
    before = {n: p.detach().clone() for n, p in backbone.named_parameters()}
    train_step(model, tokenizer, [record], make_optimizer(model, 1e-2, 1e-2))
    changed = [n for n, p in backbone.named_parameters() if not torch.equal(before[n], p)]
    assert changed and all("lora_" in name for name in changed)


def test_semantic_targets_survive_permutation_and_soft_labels(record):
    shuffled = shuffled_record(record, random.Random(3))
    logits = [torch.tensor([{"negative": -1.0, "positive": 2.0, "false": 0.0, "true": 1.0, "0": -2.0, "1": 0.0, "2": 2.0}[label] for label in spec["criteria"]]) for spec in shuffled["questions"].values()]
    hard = decision_loss(logits, shuffled)
    soft_record = copy.deepcopy(shuffled)
    for name, spec in soft_record["questions"].items():
        gold = record["answers"][name]["label"]
        soft_record["answers"][name] = {"probabilities": {label: float(label == gold) for label in spec["criteria"]}}
    assert torch.allclose(hard, decision_loss(logits, soft_record))
    response = typed_outputs(logits, shuffled)
    assert response["mood"]["label"] == "positive"
    assert response["rating"]["label"] == "2"


def test_gold_answers_do_not_enter_inputs(record):
    backbone, tokenizer, pooling = tiny_backbone("qwen2", [record])
    model = DecisionModel(backbone, "joint", pooling).eval()
    changed = copy.deepcopy(record)
    changed["answers"]["mood"]["label"] = "negative"
    for a, b in zip(model(record, tokenizer), model(changed, tokenizer), strict=True):
        assert torch.equal(a, b)
    with pytest.raises(ValueError, match="max_length"):
        model(record, tokenizer, max_length=2)


def test_source_group_overlap_is_rejected(record):
    with pytest.raises(ValueError, match="source group"):
        check_splits([record], [record])
