import copy

import torch

from proof_lm.lora import (
    LoRALinear,
    adapter_state_dict,
    inject_lora,
    merge_lora,
    trainable_parameter_count,
    unmerge_lora,
)
from proof_lm.model import DecoderConfig, ProofLM
from proof_lm.posttraining import (
    ChatMessage,
    dpo_loss,
    group_normalized_advantages,
    serialize_chat,
    verifier_reward,
)
from proof_lm.tools import ProofToolRegistry, ToolCall


def test_chat_serialization_masks_assistant_tokens_only() -> None:
    encoded = serialize_chat(
        [ChatMessage("user", "hi"), ChatMessage("assistant", "ok")],
        lambda text: [ord(value) for value in text],
        {"bos": 0, "eot": 1, "role_user": 2, "role_assistant": 3},
    )
    assert encoded.token_ids == (0, 2, 104, 105, 1, 3, 111, 107, 1)
    assert encoded.loss_mask == (False, False, False, False, False, False, True, True, True)
    assert encoded.spans[-1].supervised


def test_dpo_and_group_advantage_contracts() -> None:
    loss = dpo_loss(
        torch.tensor([2.0, 1.0]),
        torch.tensor([1.0, 1.0]),
        torch.tensor([1.0, 1.0]),
        torch.tensor([1.0, 1.0]),
        beta=0.5,
    )
    assert loss.shape == (2,)
    advantages = group_normalized_advantages([0.0, 1.0, 2.0])
    torch.testing.assert_close(advantages.mean(), torch.tensor(0.0), atol=1e-6, rtol=0)
    assert verifier_reward("not a proof") == 0.0


def test_typed_proof_tools_validate_and_execute() -> None:
    registry = ProofToolRegistry()
    assert registry.registry_id.startswith("tools-")
    parsed = registry.execute(ToolCall("parse_formula", {"formula": "P -> Q"}))
    assert parsed.ok and parsed.value["kind"] == "implies"
    missing = registry.execute(ToolCall("check_proof", {}))
    assert not missing.ok and missing.error_code == "missing_argument"
    unknown = registry.execute(ToolCall("not_a_tool", {}))
    assert not unknown.ok and unknown.error_code == "unknown_tool"


def test_lora_is_zero_impact_at_initialization_and_merges_reversibly() -> None:
    torch.manual_seed(4)
    base = torch.nn.Linear(5, 3)
    wrapped = LoRALinear(copy.deepcopy(base), rank=2, alpha=4)
    values = torch.randn(2, 5)
    torch.testing.assert_close(wrapped(values), base(values))
    assert trainable_parameter_count(wrapped) == 2 * (5 + 3)
    wrapped.lora_B.data.normal_()
    before = wrapped(values).detach()
    merge_lora(wrapped)
    merged = wrapped(values).detach()
    torch.testing.assert_close(before, merged)
    unmerge_lora(wrapped)
    torch.testing.assert_close(wrapped(values), before)
    assert set(adapter_state_dict(wrapped)) == {"lora_A", "lora_B"}


def test_lora_injection_reduces_trainable_surface() -> None:
    model = ProofLM(
        DecoderConfig(
            vocab_size=17,
            context_length=8,
            n_layers=1,
            d_model=16,
            n_heads=2,
            d_ff=32,
        )
    )
    original = model.parameter_count
    names = inject_lora(model, rank=2, target_names=("blocks.0.attention.output",))
    assert names == ("blocks.0.attention.output",)
    assert trainable_parameter_count(model) < original
    assert isinstance(model.get_submodule("blocks.0.attention.output"), LoRALinear)
