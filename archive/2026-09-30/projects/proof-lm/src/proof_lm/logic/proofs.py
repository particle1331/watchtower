"""Natural-deduction proof objects and an independent line verifier."""

from __future__ import annotations

from dataclasses import dataclass

from .formula import Formula, bottom, conjunction


@dataclass(frozen=True, slots=True)
class ProofLine:
    line_no: int
    formula: Formula
    rule: str
    references: tuple[int, ...] = ()
    open_assumptions: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class Proof:
    premises: tuple[Formula, ...]
    goal: Formula
    lines: tuple[ProofLine, ...]


@dataclass(frozen=True, slots=True)
class VerificationResult:
    valid: bool
    errors: tuple[str, ...]
    final_open_assumptions: tuple[int, ...] = ()


def _union(*values: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(sorted({item for value in values for item in value}))


def verify_proof(proof: Proof) -> VerificationResult:
    """Check line references, rule premises, scopes, goal, and discharge."""

    errors: list[str] = []
    derived: dict[int, tuple[int, ...]] = {}
    formulas: dict[int, Formula] = {}

    def error(code: str, line: ProofLine) -> None:
        errors.append(f"{code}: line {line.line_no}")

    for expected_no, line in enumerate(proof.lines, start=1):
        if line.line_no != expected_no:
            error("line_numbers_not_consecutive", line)
        if any(reference >= line.line_no or reference not in formulas for reference in line.references):
            error("reference_must_be_prior_line", line)
            derived_open = ()
        else:
            derived_open = _union(*(derived[reference] for reference in line.references))
        rule = line.rule
        references = line.references
        expected_open = derived_open

        if rule == "premise":
            if references or line.formula not in proof.premises:
                error("invalid_premise", line)
            expected_open = ()
        elif rule == "assumption":
            if references:
                error("assumption_has_references", line)
            expected_open = (line.line_no,)
        elif rule == "reiteration":
            if len(references) != 1 or formulas.get(references[0]) != line.formula:
                error("invalid_reiteration", line)
        elif rule == "conjunction_introduction":
            if not (
                len(references) == 2
                and all(reference in formulas for reference in references)
                and line.formula == conjunction(formulas[references[0]], formulas[references[1]])
            ):
                error("invalid_conjunction_introduction", line)
        elif rule in {"conjunction_elimination_left", "conjunction_elimination_right"}:
            if len(references) != 1 or formulas.get(references[0], Formula("bottom")) .kind != "and":
                error("conjunction_elimination_needs_conjunction", line)
            elif rule.endswith("left") and line.formula != formulas[references[0]].left:
                error("wrong_left_conjunct", line)
            elif rule.endswith("right") and line.formula != formulas[references[0]].right:
                error("wrong_right_conjunct", line)
        elif rule in {"disjunction_introduction_left", "disjunction_introduction_right"}:
            if len(references) != 1 or formulas.get(references[0]) is None:
                error("invalid_disjunction_introduction", line)
            elif rule.endswith("left") and (
                line.formula.kind != "or" or line.formula.left != formulas[references[0]]
            ):
                error("wrong_left_disjunct", line)
            elif rule.endswith("right") and (
                line.formula.kind != "or" or line.formula.right != formulas[references[0]]
            ):
                error("wrong_right_disjunct", line)
        elif rule == "implication_elimination":
            if len(references) != 2:
                error("implication_elimination_needs_two_references", line)
            else:
                implication_line = formulas.get(references[0])
                argument = formulas.get(references[1])
                if (
                    implication_line is None
                    or implication_line.kind != "implies"
                    or argument != implication_line.left
                    or line.formula != implication_line.right
                ):
                    error("invalid_implication_elimination", line)
        elif rule == "implication_introduction":
            if len(references) != 2:
                error("implication_introduction_needs_assumption_and_body", line)
            else:
                assumption, body = references
                if (
                    formulas.get(assumption) is None
                    or formulas[assumption] != line.formula.left
                    if line.formula.kind == "implies"
                    else True
                ):
                    error("invalid_implication_introduction_formula", line)
                if body not in derived or assumption not in derived[body]:
                    error("implication_introduction_missing_discharge", line)
                elif line.formula.kind != "implies" or formulas.get(body) != line.formula.right:
                    error("invalid_implication_introduction_body", line)
                expected_open = tuple(item for item in derived.get(body, ()) if item != assumption)
        elif rule == "negation_introduction":
            if len(references) != 2:
                error("negation_introduction_needs_assumption_and_contradiction", line)
            else:
                assumption, contradiction = references
                if formulas.get(contradiction) != bottom() or assumption not in derived.get(contradiction, ()):
                    error("invalid_negation_introduction", line)
                elif line.formula.kind != "not" or formulas.get(assumption) != line.formula.left:
                    error("invalid_negation_introduction_formula", line)
                expected_open = tuple(item for item in derived.get(contradiction, ()) if item != assumption)
        elif rule == "negation_elimination":
            if len(references) != 2:
                error("negation_elimination_needs_two_references", line)
            else:
                left = formulas.get(references[0])
                right = formulas.get(references[1])
                if not ((left and left.kind == "not" and left.left == right) or (right and right.kind == "not" and right.left == left)):
                    error("invalid_negation_elimination", line)
                if line.formula != bottom():
                    error("negation_elimination_returns_bottom", line)
        elif rule == "contradiction_elimination":
            if len(references) != 1 or formulas.get(references[0]) != bottom():
                error("contradiction_elimination_needs_bottom", line)
        elif rule == "disjunction_elimination":
            if len(references) != 5:
                error("disjunction_elimination_needs_five_references", line)
            else:
                disjunction_line, left_assumption, left_body, right_assumption, right_body = references
                disjunction_formula = formulas.get(disjunction_line)
                if disjunction_formula is None or disjunction_formula.kind != "or":
                    error("disjunction_elimination_needs_disjunction", line)
                elif (
                    formulas.get(left_assumption) != disjunction_formula.left
                    or formulas.get(right_assumption) != disjunction_formula.right
                    or formulas.get(left_body) != formulas.get(right_body)
                    or formulas.get(left_body) != line.formula
                    or left_assumption not in derived.get(left_body, ())
                    or right_assumption not in derived.get(right_body, ())
                ):
                    error("invalid_disjunction_elimination", line)
                expected_open = _union(
                    derived.get(disjunction_line, ()),
                    tuple(item for item in derived.get(left_body, ()) if item != left_assumption),
                    tuple(item for item in derived.get(right_body, ()) if item != right_assumption),
                )
        else:
            error("unknown_rule", line)

        actual_open = tuple(sorted(line.open_assumptions))
        if actual_open != expected_open:
            error("open_assumptions_do_not_match", line)
        derived[line.line_no] = expected_open
        formulas[line.line_no] = line.formula

    if not proof.lines:
        errors.append("empty_proof")
        final_open = ()
    else:
        final = proof.lines[-1]
        final_open = derived.get(final.line_no, ())
        if final.formula != proof.goal:
            errors.append("goal_mismatch")
        if final_open:
            errors.append("undischarged_assumptions")
    return VerificationResult(not errors, tuple(errors), final_open)


def render_proof(proof: Proof) -> str:
    """Render a proof with enough metadata for a parser round trip."""

    premise_lines = [f"{index}. {formula}" for index, formula in enumerate(proof.premises, start=1)]
    rendered_lines = []
    for line in proof.lines:
        tail = " ".join(str(reference) for reference in line.references)
        if line.open_assumptions:
            tail = f"{tail} open {' '.join(map(str, line.open_assumptions))}".strip()
        rendered_lines.append(f"{line.line_no}. {line.formula} ; {line.rule}{(' ' + tail) if tail else ''}")
    return "\n".join(
        [
            "<theorem>",
            "premises:",
            *premise_lines,
            f"goal: {proof.goal}",
            "</theorem>",
            "<proof>",
            *rendered_lines,
            "</proof>",
        ]
    )
