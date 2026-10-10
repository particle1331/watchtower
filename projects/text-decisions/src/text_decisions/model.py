"""Small, ordinary-PyTorch decision heads; no Unsloth or AnyJev dependency."""

from dataclasses import dataclass
from typing import Any

import torch
from torch import Tensor, nn
from torch.nn import functional as F

TYPE_IDS = {"choice": 0, "noul": 1, "score": 2}


@dataclass
class Question:
    name: str
    kind: str
    instructions: str
    labels: list[str]
    descriptions: list[str]


def questions_from(record: dict[str, Any]) -> list[Question]:
    """Validate the schema before constructing model input. Answers are separate."""
    if not isinstance(record.get("state"), str) or not record["state"].strip():
        raise ValueError("state must be nonempty text")
    questions = []
    for name, spec in record["questions"].items():
        kind = spec["type"]
        criteria = spec["criteria"]
        if kind not in TYPE_IDS or not criteria:
            raise ValueError("unknown type or empty candidate set")
        labels = list(criteria)
        if kind == "noul" and set(labels) != {"false", "true"}:
            raise ValueError("noul criteria must be false and true")
        if kind == "score" and set(labels) != {str(i) for i in range(len(labels))}:
            raise ValueError("score labels must be zero-based consecutive levels")
        descriptions = list(criteria.values())
        if not spec["instructions"].strip() or any(not s.strip() for s in descriptions):
            raise ValueError("instructions and descriptions must be nonempty")
        questions.append(Question(name, kind, spec["instructions"], labels, descriptions))
    if not questions:
        raise ValueError("at least one question is required")
    return questions


def candidate_texts(state: str, questions: list[Question]) -> list[str]:
    return [
        f"State: {state}\nQuestion: {q.instructions}\n"
        f"Candidate: {label}: {description}\nDecision:"
        for q in questions
        for label, description in zip(q.labels, q.descriptions, strict=True)
    ]


def joint_text(state: str, questions: list[Question]) -> tuple[str, list[tuple[int, int]], list[list[tuple[int, int]]]]:
    """Track character spans while writing the input; never include gold answers."""
    text = f"State: {state}\n"
    question_spans = []
    option_spans = []
    for q in questions:
        text += f"\nType: {q.kind}\nQuestion: "
        start = len(text)
        text += q.instructions
        question_spans.append((start, len(text)))
        spans = []
        for label, description in zip(q.labels, q.descriptions, strict=True):
            text += "\nOption: "
            start = len(text)
            text += f"{label}: {description}"
            spans.append((start, len(text)))
        option_spans.append(spans)
        text += "\n"
    return text, question_spans, option_spans


def token_span(offsets: list[tuple[int, int]], span: tuple[int, int]) -> tuple[int, int]:
    """Map a character span to all overlapping tokens of the complete input."""
    start, end = span
    indices = [i for i, (a, b) in enumerate(offsets) if a < end and b > start]
    if not indices:
        raise ValueError("a question or option has no tokens")
    return indices[0], indices[-1] + 1


def readout(hidden: Tensor, attention_mask: Tensor, pooling: str) -> Tensor:
    """[batch, tokens, features] -> [batch, features], excluding padding."""
    valid = attention_mask.bool()
    if not valid.any(dim=1).all():
        raise ValueError("empty sequence")
    if pooling == "last":
        positions = torch.arange(hidden.size(1), device=hidden.device)
        last = positions.expand_as(valid).masked_fill(~valid, -1).max(dim=1).values
        return hidden[torch.arange(hidden.size(0), device=hidden.device), last]
    if pooling == "mean":
        weights = valid.unsqueeze(-1).to(hidden.dtype)
        return (hidden * weights).sum(dim=1) / weights.sum(dim=1)
    raise ValueError("pooling must be last or mean")


class CandidateHead(nn.Module):
    def __init__(self, hidden_size: int, width: int = 32):
        super().__init__()
        self.scorer = nn.Sequential(nn.Linear(hidden_size, width), nn.GELU(), nn.Linear(width, 1))

    def forward(self, hidden: Tensor, mask: Tensor, pooling: str) -> Tensor:
        return self.scorer(readout(hidden, mask, pooling)).squeeze(-1)


class JointHead(nn.Module):
    """One record: span pooling -> evidence attention -> question interaction -> logits."""
    def __init__(self, hidden_size: int, width: int = 32, heads: int = 4):
        super().__init__()
        self.project = nn.Linear(hidden_size, width)
        self.evidence = nn.MultiheadAttention(width, heads, dropout=0.0, batch_first=True)
        self.norm = nn.LayerNorm(width)
        self.ff = nn.Sequential(nn.Linear(width, 2 * width), nn.GELU(), nn.Linear(2 * width, width))
        self.ff_norm = nn.LayerNorm(width)
        self.type_embedding = nn.Embedding(3, width)
        self.interact = nn.TransformerDecoderLayer(width, heads, 2 * width, dropout=0.0, batch_first=True)
        self.scorer = nn.Sequential(nn.Linear(4 * width, width), nn.GELU(), nn.Linear(width, 1))

    def forward(self, hidden: Tensor, question_spans: list[tuple[int, int]],
                option_spans: list[list[tuple[int, int]]], kinds: list[int]) -> list[Tensor]:
        # This readable per-record path has no padded tokens or padded options.
        memory = self.project(hidden)
        question = torch.stack([memory[a:b].mean(dim=0) for a, b in question_spans])
        options = [torch.stack([memory[a:b].mean(dim=0) for a, b in spans]) for spans in option_spans]
        queries = torch.cat([o + q for o, q in zip(options, question, strict=True)])
        evidence, _ = self.evidence(queries[None], memory[None], memory[None], need_weights=False)
        routed = self.norm(queries + evidence[0])
        routed = self.ff_norm(routed + self.ff(routed))
        routed_options = list(routed.split([len(o) for o in options]))
        type_ids = torch.tensor(kinds, device=hidden.device)
        summaries = torch.stack([o.mean(dim=0) for o in routed_options])
        question = question + summaries + self.type_embedding(type_ids)
        # No causal head mask: all questions may interact with all questions/memory.
        question = self.interact(question[None], memory[None])[0]
        logits = []
        for q, o in zip(question, routed_options, strict=True):
            q = q.expand_as(o)
            features = torch.cat([q, o, q * o, (q - o).abs()], dim=-1)
            logits.append(self.scorer(features).squeeze(-1))
        return logits


class DecisionModel(nn.Module):
    def __init__(self, backbone: Any, head: str, pooling: str, width: int = 32):
        super().__init__()
        self.backbone = backbone
        self.head_name, self.pooling, self.width = head, pooling, width
        hidden_size = backbone.config.hidden_size
        if head == "candidate":
            self.head = CandidateHead(hidden_size, width)
        elif head == "joint":
            self.head = JointHead(hidden_size, width)
        else:
            raise ValueError("head must be candidate or joint")

    def forward(self, record: dict[str, Any], tokenizer: Any, max_length: int = 512) -> list[Tensor]:
        questions = questions_from(record)
        device = next(self.parameters()).device
        if self.head_name == "candidate":
            texts = candidate_texts(record["state"], questions)
            encoded = tokenizer(texts, padding=True, truncation=False, return_tensors="pt")
            if encoded.input_ids.size(1) > max_length:
                raise ValueError("input exceeds max_length; chunk/shorten the state explicitly")
            inputs = {k: v.to(device) for k, v in encoded.items() if k in {"input_ids", "attention_mask"}}
            hidden = self.backbone(**inputs).last_hidden_state
            scores = self.head(hidden, inputs["attention_mask"], self.pooling)
            return list(scores.split([len(q.labels) for q in questions]))
        text, q_chars, o_chars = joint_text(record["state"], questions)
        encoded = tokenizer(text, return_offsets_mapping=True, truncation=False, return_tensors="pt")
        if encoded.input_ids.size(1) > max_length:
            raise ValueError("input exceeds max_length; preserve the question schema when shortening")
        offsets = encoded.pop("offset_mapping")[0].tolist()
        q_spans = [token_span(offsets, s) for s in q_chars]
        o_spans = [[token_span(offsets, s) for s in spans] for spans in o_chars]
        inputs = {k: v.to(device) for k, v in encoded.items() if k in {"input_ids", "attention_mask"}}
        hidden = self.backbone(**inputs).last_hidden_state[0]
        return self.head(hidden, q_spans, o_spans, [TYPE_IDS[q.kind] for q in questions])


def decision_loss(logits: list[Tensor], record: dict[str, Any]) -> Tensor:
    """Mean question loss per record. Supports gold labels or audited soft targets."""
    losses = []
    for scores, q in zip(logits, questions_from(record), strict=True):
        answer = record["answers"][q.name]
        if "probabilities" in answer:
            probs = answer["probabilities"]
            if set(probs) != set(q.labels):
                raise ValueError("target distribution must name exactly the allowed labels")
            target = scores.new_tensor([probs[label] for label in q.labels]).float()
            if not torch.isfinite(target).all() or (target < 0).any() or not torch.isclose(target.sum(), target.new_tensor(1.0)):
                raise ValueError("target must be a finite probability distribution")
            losses.append(-(target * F.log_softmax(scores.float(), dim=-1)).sum())
        else:
            target_index = q.labels.index(answer["label"])
            target = torch.tensor([target_index], device=scores.device)
            losses.append(F.cross_entropy(scores.float()[None], target))
    return torch.stack(losses).mean()


def typed_outputs(logits: list[Tensor], record: dict[str, Any]) -> dict[str, Any]:
    result = {}
    for scores, q in zip(logits, questions_from(record), strict=True):
        values = scores.detach().float().softmax(dim=-1).cpu().tolist()
        distribution = dict(zip(q.labels, values, strict=True))
        item: dict[str, Any] = {"label": q.labels[max(range(len(values)), key=values.__getitem__)], "probabilities": distribution}
        if q.kind == "noul":
            item["true_probability"] = distribution["true"]
        if q.kind == "score":
            item["expected_level"] = sum(int(label) * p for label, p in distribution.items())
        result[q.name] = item
    return result


def restricted_label_loss(vocab_logits: Tensor, label_ids: Tensor, targets: Tensor) -> Tensor:
    """AnyJev-inspired supervised extension: CE over allowed answer-token logits."""
    option_logits = vocab_logits.index_select(-1, label_ids)
    return F.cross_entropy(option_logits.float(), targets)
