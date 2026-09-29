"""Immutable propositional formula trees and canonical rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FormulaKind = Literal["atom", "bottom", "not", "and", "or", "implies"]


@dataclass(frozen=True, slots=True)
class Formula:
    """A small AST for the course's propositional language."""

    kind: FormulaKind
    name: str | None = None
    left: Formula | None = None
    right: Formula | None = None

    def __post_init__(self) -> None:
        if self.kind == "atom":
            if not self.name or self.left is not None or self.right is not None:
                raise ValueError("an atom needs a name and no children")
        elif self.kind == "bottom":
            if self.name is not None or self.left is not None or self.right is not None:
                raise ValueError("bottom has no name or children")
        elif self.kind == "not":
            if self.left is None or self.right is not None or self.name is not None:
                raise ValueError("negation needs exactly one child")
        elif self.kind in {"and", "or", "implies"} and (
            self.left is None or self.right is None or self.name is not None
        ):
            raise ValueError(f"{self.kind} needs exactly two children")

    def atoms(self) -> frozenset[str]:
        """Return the atom names occurring in the formula."""

        if self.kind == "atom":
            return frozenset({self.name})  # type: ignore[arg-type]
        if self.kind == "bottom":
            return frozenset()
        if self.kind == "not":
            return self.left.atoms()  # type: ignore[union-attr]
        return self.left.atoms() | self.right.atoms()  # type: ignore[union-attr]

    def evaluate(self, valuation: dict[str, bool]) -> bool:
        """Evaluate the formula under a total or partial valuation."""

        if self.kind == "atom":
            if self.name not in valuation:
                raise KeyError(f"valuation has no value for {self.name!r}")
            return valuation[self.name]  # type: ignore[index]
        if self.kind == "bottom":
            return False
        if self.kind == "not":
            return not self.left.evaluate(valuation)  # type: ignore[union-attr]
        if self.kind == "and":
            return self.left.evaluate(valuation) and self.right.evaluate(valuation)  # type: ignore[union-attr]
        if self.kind == "or":
            return self.left.evaluate(valuation) or self.right.evaluate(valuation)  # type: ignore[union-attr]
        return (not self.left.evaluate(valuation)) or self.right.evaluate(valuation)  # type: ignore[union-attr]

    def __str__(self) -> str:
        return render_formula(self)


def atom(name: str) -> Formula:
    if not name or not name.replace("_", "a").isalnum() or not name[0].isalpha():
        raise ValueError("atom names must start with a letter and contain letters, digits, or _")
    return Formula("atom", name=name)


def bottom() -> Formula:
    return Formula("bottom")


def negation(value: Formula) -> Formula:
    return Formula("not", left=value)


def conjunction(left: Formula, right: Formula) -> Formula:
    return Formula("and", left=left, right=right)


def disjunction(left: Formula, right: Formula) -> Formula:
    return Formula("or", left=left, right=right)


def implication(left: Formula, right: Formula) -> Formula:
    return Formula("implies", left=left, right=right)


def _precedence(value: Formula) -> int:
    return {"implies": 1, "or": 2, "and": 3, "not": 4, "atom": 5, "bottom": 5}[value.kind]


def render_formula(value: Formula, parent_precedence: int = 0) -> str:
    """Render a formula using the canonical Unicode surface form."""

    precedence = _precedence(value)
    if value.kind == "atom":
        text = value.name or ""
    elif value.kind == "bottom":
        text = "⊥"
    elif value.kind == "not":
        child = render_formula(value.left, precedence)  # type: ignore[arg-type]
        text = f"¬{child}"
    else:
        operator = {"and": "∧", "or": "∨", "implies": "→"}[value.kind]
        left = render_formula(value.left, precedence)  # type: ignore[arg-type]
        right_parent = precedence - 1 if value.kind == "implies" else precedence
        right = render_formula(value.right, right_parent)  # type: ignore[arg-type]
        text = f"{left} {operator} {right}"
    if precedence < parent_precedence:
        return f"({text})"
    return text
