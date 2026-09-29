"""Truth-table semantics and checked countermodel search."""

from __future__ import annotations

from itertools import product

from .formula import Formula


def truth_table(formulas: tuple[Formula, ...] | list[Formula]) -> list[tuple[dict[str, bool], tuple[bool, ...]]]:
    """Evaluate formulas on every assignment in sorted atom order."""

    formulas = tuple(formulas)
    names = sorted({name for formula in formulas for name in formula.atoms()})
    rows = []
    for values in product((False, True), repeat=len(names)):
        valuation = dict(zip(names, values, strict=True))
        rows.append((valuation, tuple(formula.evaluate(valuation) for formula in formulas)))
    return rows


def find_countermodel(premises: tuple[Formula, ...] | list[Formula], goal: Formula) -> dict[str, bool] | None:
    """Find an assignment satisfying every premise and falsifying the goal."""

    formulas = tuple(premises) + (goal,)
    for valuation, values in truth_table(formulas):
        if all(values[:-1]) and not values[-1]:
            return valuation
    return None


def entails(premises: tuple[Formula, ...] | list[Formula], goal: Formula) -> bool:
    """Return whether the premises truth-table entail the goal."""

    return find_countermodel(premises, goal) is None
