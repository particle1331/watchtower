"""Deterministic verified proof fixtures for the course data contract."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from .formula import Formula, atom, conjunction, implication
from .proofs import Proof, ProofLine, render_proof, verify_proof
from .semantics import find_countermodel


@dataclass(frozen=True, slots=True)
class GeneratedExample:
    example_id: str
    kind: str
    theorem_family: str
    proof_shape: str
    proof_depth: int
    variable_family: str
    paraphrase_template: str
    perturbation: str
    tool_schema: str
    premises: tuple[Formula, ...]
    goal: Formula
    proof: Proof
    proof_text: str
    countermodel: dict[str, bool] | None

    @property
    def structural_key(self) -> tuple[str, ...]:
        return (
            self.theorem_family,
            self.proof_shape,
            str(self.proof_depth),
            self.variable_family,
            self.paraphrase_template,
            self.perturbation,
            self.tool_schema,
        )


def _line(
    line_no: int,
    formula: Formula,
    rule: str,
    references: tuple[int, ...] = (),
    open_assumptions: tuple[int, ...] = (),
) -> ProofLine:
    return ProofLine(line_no, formula, rule, references, open_assumptions)


def _template(index: int, variable_family: str) -> tuple[str, Proof]:
    names = {
        "pq": ("P", "Q", "R"),
        "abc": ("A", "B", "C"),
        "xyz": ("X", "Y", "Z"),
        "uvw": ("U", "V", "W"),
    }[variable_family]
    first, second, third = map(atom, names)
    choice = index % 5
    if choice == 0:
        proof = Proof(
            premises=(first,),
            goal=first,
            lines=(
                _line(1, first, "premise"),
                _line(2, first, "reiteration", (1,)),
            ),
        )
        return "reiteration", proof
    if choice == 1:
        arrow = implication(first, second)
        proof = Proof(
            premises=(arrow, first),
            goal=second,
            lines=(
                _line(1, arrow, "premise"),
                _line(2, first, "premise"),
                _line(3, second, "implication_elimination", (1, 2)),
            ),
        )
        return "implication_elimination", proof
    if choice == 2:
        pair = conjunction(first, second)
        proof = Proof(
            premises=(pair,),
            goal=first,
            lines=(
                _line(1, pair, "premise"),
                _line(2, first, "conjunction_elimination_left", (1,)),
            ),
        )
        return "conjunction_elimination_left", proof
    if choice == 3:
        proof = Proof(
            premises=(first, second),
            goal=conjunction(first, second),
            lines=(
                _line(1, first, "premise"),
                _line(2, second, "premise"),
                _line(3, conjunction(first, second), "conjunction_introduction", (1, 2)),
            ),
        )
        return "conjunction_introduction", proof
    proof = Proof(
        premises=(),
        goal=implication(first, first),
        lines=(
            _line(1, first, "assumption", open_assumptions=(1,)),
            _line(2, first, "reiteration", (1,), (1,)),
            _line(3, implication(first, first), "implication_introduction", (1, 2)),
        ),
    )
    return "implication_introduction", proof


def _example(index: int, variable_family: str, paraphrase_template: str) -> GeneratedExample:
    proof_shape, proof = _template(index, variable_family)
    result = verify_proof(proof)
    if not result.valid:
        raise AssertionError(f"generator produced invalid positive proof: {result.errors}")
    family = proof_shape.removesuffix("_left").removesuffix("_right")
    return GeneratedExample(
        example_id=f"positive-{index:04d}",
        kind="positive",
        theorem_family=family,
        proof_shape=proof_shape,
        proof_depth=len(proof.lines),
        variable_family=variable_family,
        paraphrase_template=paraphrase_template,
        perturbation="none",
        tool_schema="proof-tools-v1",
        premises=proof.premises,
        goal=proof.goal,
        proof=proof,
        proof_text=render_proof(proof),
        countermodel=None,
    )


def _invalid_reference(example: GeneratedExample) -> GeneratedExample:
    last = example.proof.lines[-1]
    if last.references:
        bad_reference = max((line.line_no for line in example.proof.lines), default=0) + 1
        bad_last = replace(last, references=(bad_reference, *last.references[1:]))
    else:
        bad_last = replace(last, formula=atom("Invalid"))
    bad_proof = replace(example.proof, lines=(*example.proof.lines[:-1], bad_last))
    return replace(
        example,
        example_id=example.example_id.replace("positive", "negative-reference"),
        kind="negative",
        perturbation="invalid_reference",
        proof=bad_proof,
        proof_text=render_proof(bad_proof),
    )


def _wrong_goal(example: GeneratedExample) -> GeneratedExample:
    used = example.goal.atoms() | {name for premise in example.premises for name in premise.atoms()}
    candidate = next(name for name in ("P", "Q", "R", "S", "T", "Z") if name not in used)
    goal = atom(candidate)
    countermodel = find_countermodel(example.premises, goal)
    if countermodel is None:
        raise AssertionError("wrong-goal perturbation needs a countermodel")
    bad_proof = replace(example.proof, goal=goal)
    return replace(
        example,
        example_id=example.example_id.replace("positive", "negative-goal"),
        kind="negative",
        perturbation="wrong_goal",
        goal=goal,
        proof=bad_proof,
        proof_text=render_proof(bad_proof),
        countermodel=countermodel,
    )


def generate_examples(count: int = 20, seed: int = 17) -> list[GeneratedExample]:
    """Generate verified positives and controlled invalid examples."""

    if count < 1:
        raise ValueError("count must be positive")
    rng = random.Random(seed)
    families = ("pq", "abc", "xyz", "uvw")
    positives = [
        _example(index, rng.choice(families), f"render-{index % 2}") for index in range(count)
    ]
    negatives = []
    for example in positives:
        negatives.extend((_invalid_reference(example), _wrong_goal(example)))
    return positives + negatives
