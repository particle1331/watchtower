"""Deterministic typed tools used by the tool-calling course chapters."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .identity import identity
from .logic import find_countermodel, parse_formula, parse_proof, verify_proof


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    required_arguments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    ok: bool
    value: dict[str, Any]
    error_code: str | None = None


class ProofToolRegistry:
    """A small registry whose failures are structured training examples."""

    specs = (
        ToolSpec("parse_formula", "Parse a propositional formula.", ("formula",)),
        ToolSpec("check_proof", "Check a rendered natural-deduction proof.", ("proof",)),
        ToolSpec(
            "find_countermodel",
            "Find a valuation refuting premise entailment.",
            ("premises", "goal"),
        ),
    )

    @property
    def registry_id(self) -> str:
        return identity(
            "tools",
            [
                {
                    "name": spec.name,
                    "description": spec.description,
                    "required_arguments": spec.required_arguments,
                }
                for spec in self.specs
            ],
        )

    def schema(self) -> tuple[dict[str, Any], ...]:
        """Return a JSON-schema-like inventory suitable for a prompt."""

        return tuple(
            {
                "name": spec.name,
                "description": spec.description,
                "required": list(spec.required_arguments),
            }
            for spec in self.specs
        )

    def execute(self, call: ToolCall) -> ToolResult:
        """Validate a call and execute it without leaking Python exceptions."""

        spec = next((item for item in self.specs if item.name == call.name), None)
        if spec is None:
            return ToolResult(False, {}, "unknown_tool")
        missing = [name for name in spec.required_arguments if name not in call.arguments]
        if missing:
            return ToolResult(False, {"missing": missing}, "missing_argument")
        try:
            if call.name == "parse_formula":
                formula = parse_formula(_string(call.arguments, "formula"))
                return ToolResult(True, {"formula": str(formula), "kind": formula.kind})
            if call.name == "check_proof":
                result = verify_proof(parse_proof(_string(call.arguments, "proof")))
                return ToolResult(True, {"valid": result.valid, "errors": list(result.errors)})
            premises = tuple(parse_formula(value) for value in _strings(call.arguments, "premises"))
            goal = parse_formula(_string(call.arguments, "goal"))
            countermodel = find_countermodel(premises, goal)
            return ToolResult(
                True,
                {"entailed": countermodel is None, "countermodel": countermodel},
            )
        except (TypeError, ValueError):
            return ToolResult(False, {}, "invalid_arguments")


def _string(arguments: Mapping[str, Any], name: str) -> str:
    value = arguments[name]
    if not isinstance(value, str):
        raise TypeError(name)
    return value


def _strings(arguments: Mapping[str, Any], name: str) -> list[str]:
    value = arguments[name]
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(name)
    return value
