from pathlib import Path

import torch

from proof_lm.baselines import (
    TorchBigramLM,
    TorchContextMLP,
    make_context_dataset,
    train_classifier,
)
from proof_lm.data import batch_packed_examples, pack_causal_examples
from proof_lm.evaluation import evaluate_language_model
from proof_lm.model import DecoderConfig, ProofLM
from proof_lm.optimization import (
    adamw_parameter_groups,
    clip_gradients,
    warmup_cosine_factor,
)
from proof_lm.trainer import (
    load_training_checkpoint,
    save_training_checkpoint,
    train_batches,
)


def small_model() -> ProofLM:
    return ProofLM(
        DecoderConfig(
            vocab_size=19,
            context_length=8,
            n_layers=1,
            d_model=16,
            n_heads=2,
            d_ff=32,
        )
    )


def test_decoder_shapes_causality_weight_tying_and_generation() -> None:
    torch.manual_seed(5)
    model = small_model().eval()
    inputs = torch.tensor([[1, 2, 3, 4]])
    logits, loss = model(inputs)
    assert logits.shape == (1, 4, 19)
    assert loss is None
    assert model.embeddings_are_tied
    changed = inputs.clone()
    changed[0, -1] = 8
    changed_logits = model(changed)[0]
    torch.testing.assert_close(logits[:, :-1], changed_logits[:, :-1])

    first_generator = torch.Generator().manual_seed(11)
    second_generator = torch.Generator().manual_seed(11)
    first = model.generate(inputs[:, :2], 3, top_k=4, generator=first_generator)
    second = model.generate(inputs[:, :2], 3, top_k=4, generator=second_generator)
    assert first.shape == (1, 5)
    torch.testing.assert_close(first, second)


def test_torch_baselines_reduce_loss_on_their_training_batch() -> None:
    torch.manual_seed(3)
    inputs, targets = make_context_dataset([0, 1, 0, 1] * 12, context_length=2)
    bigram_inputs, bigram_targets = inputs[:, -1], targets
    bigram = TorchBigramLM(vocab_size=2)
    bigram_losses = train_classifier(
        bigram, bigram_inputs, bigram_targets, steps=20, learning_rate=0.1
    )
    mlp = TorchContextMLP(vocab_size=2, context_length=2, embedding_dim=4, hidden_dim=8)
    mlp_losses = train_classifier(mlp, inputs, targets, steps=20, learning_rate=0.05)
    assert bigram_losses[-1] < bigram_losses[0]
    assert mlp_losses[-1] < mlp_losses[0]


def test_masked_loss_excludes_padding_positions() -> None:
    torch.manual_seed(7)
    model = small_model()
    inputs = torch.tensor([[1, 2, 3, 0]])
    labels = torch.tensor([[2, 3, 4, 0]])
    _, full_loss = model(inputs, labels=labels)
    _, masked_loss = model(
        inputs,
        labels=labels,
        loss_mask=torch.tensor([[True, True, True, False]]),
    )
    assert full_loss is not None and masked_loss is not None
    assert torch.isfinite(masked_loss)
    assert not torch.equal(full_loss, masked_loss)


def test_checkpoint_resume_matches_uninterrupted_training(tmp_path: Path) -> None:
    torch.manual_seed(13)
    examples = pack_causal_examples(
        [[1, 2, 3, 4, 5], [6, 7, 8, 9]],
        eos_id=18,
        pad_id=0,
        context_length=8,
        stride=8,
    )
    batches = batch_packed_examples(examples, batch_size=1)
    uninterrupted = small_model()
    interrupted = small_model()
    interrupted.load_state_dict(uninterrupted.state_dict())
    resumed = small_model()
    optimizer_a = torch.optim.AdamW(uninterrupted.parameters(), lr=0.01)
    optimizer_b = torch.optim.AdamW(interrupted.parameters(), lr=0.01)
    optimizer_c = torch.optim.AdamW(resumed.parameters(), lr=0.01)

    final_state, _ = train_batches(uninterrupted, batches, optimizer_a)
    first_state, _ = train_batches(interrupted, batches[:1], optimizer_b)
    checkpoint = tmp_path / "resume.pt"
    save_training_checkpoint(checkpoint, interrupted, optimizer_b, first_state)
    loaded_state = load_training_checkpoint(checkpoint, resumed, optimizer_c)
    assert loaded_state == first_state
    resumed_state, _ = train_batches(
        resumed, batches[1:], optimizer_c, state=loaded_state
    )
    assert resumed_state == final_state
    for name, parameter in uninterrupted.state_dict().items():
        torch.testing.assert_close(parameter, resumed.state_dict()[name])


def test_language_evaluator_reports_masked_loss() -> None:
    torch.manual_seed(17)
    model = small_model()
    examples = pack_causal_examples(
        [[1, 2, 3], [4, 5, 6]],
        eos_id=18,
        pad_id=0,
        context_length=6,
    )
    report = evaluate_language_model(model, batch_packed_examples(examples, 2))
    assert float(report["tokens"]) > 0
    assert float(report["perplexity"]) > 0
    assert str(report["evaluator_id"]).startswith("eval-")


def test_schedule_clipping_and_optimizer_groups_are_explicit() -> None:
    assert warmup_cosine_factor(0, warmup_updates=2, total_updates=10) == 0.5
    assert warmup_cosine_factor(10, warmup_updates=2, total_updates=10) == 0.1
    model = small_model()
    optimizer = torch.optim.AdamW(adamw_parameter_groups(model, 0.1), lr=0.01)
    inputs = torch.tensor([[1, 2, 3]])
    labels = torch.tensor([[2, 3, 4]])
    _, loss = model(inputs, labels=labels)
    assert loss is not None
    loss.backward()
    norm = clip_gradients(model.parameters(), 0.1)
    assert norm > 0
    assert len(optimizer.param_groups) == 2
    assert optimizer.param_groups[0]["weight_decay"] == 0.1
    assert optimizer.param_groups[1]["weight_decay"] == 0.0
