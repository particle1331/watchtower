"""Recursive-descent parsers for formulas and rendered proof fixtures."""

from __future__ import annotations

import re

from .formula import Formula, atom, bottom, conjunction, disjunction, implication, negation
from .proofs import Proof, ProofLine

_TOKEN = re.compile(r"\s*(?:(?P<arrow>->|→)|(?P<atom>[A-Za-z][A-Za-z0-9_]*)|(?P<bot>⊥)|(?P<not>[¬!~])|(?P<and>[∧&])|(?P<or>[∨|])|(?P<lpar>\()|(?P<rpar>\)))")


class FormulaParser:
    def __init__(self, text: str):
        self.tokens: list[tuple[str, str]] = []
        position = 0
        while position < len(text):
            match = _TOKEN.match(text, position)
            if match is None:
                raise ValueError(f"unexpected formula text at position {position}: {text[position:]!r}")
            kind = match.lastgroup
            self.tokens.append((kind, match.group(kind)))  # type: ignore[arg-type]
            position = match.end()
        self.index = 0

    def peek(self, kind: str | None = None) -> tuple[str, str] | None:
        if self.index == len(self.tokens):
            return None
        token = self.tokens[self.index]
        return token if kind is None or token[0] == kind else None

    def take(self, kind: str) -> str:
        token = self.peek(kind)
        if token is None:
            raise ValueError(f"expected {kind}, found {self.peek()}")
        self.index += 1
        return token[1]

    def parse(self) -> Formula:
        result = self.parse_implication()
        if self.peek() is not None:
            raise ValueError(f"unexpected trailing token {self.peek()}")
        return result

    def parse_implication(self) -> Formula:
        left = self.parse_or()
        if self.peek("arrow"):
            self.take("arrow")
            return implication(left, self.parse_implication())
        return left

    def parse_or(self) -> Formula:
        result = self.parse_and()
        while self.peek("or"):
            self.take("or")
            result = disjunction(result, self.parse_and())
        return result

    def parse_and(self) -> Formula:
        result = self.parse_unary()
        while self.peek("and"):
            self.take("and")
            result = conjunction(result, self.parse_unary())
        return result

    def parse_unary(self) -> Formula:
        if self.peek("not"):
            self.take("not")
            return negation(self.parse_unary())
        if self.peek("lpar"):
            self.take("lpar")
            result = self.parse_implication()
            self.take("rpar")
            return result
        if self.peek("atom"):
            return atom(self.take("atom"))
        if self.peek("bot"):
            self.take("bot")
            return bottom()
        raise ValueError(f"expected an atom, bottom, negation, or parenthesis, found {self.peek()}")


def parse_formula(text: str) -> Formula:
    """Parse ASCII or Unicode propositional notation."""

    return FormulaParser(text).parse()


def parse_proof(text: str) -> Proof:
    """Parse the stable text emitted by :func:`render_proof`."""

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines[:2] != ["<theorem>", "premises:"]:
        raise ValueError("proof must start with <theorem> and premises:")
    end_theorem = lines.index("</theorem>")
    premise_lines = lines[2:end_theorem]
    goal_line = next((line for line in premise_lines if line.startswith("goal:")), None)
    if goal_line is None:
        raise ValueError("theorem block needs a goal")
    premises = tuple(
        parse_formula(line.split(".", 1)[1].strip())
        for line in premise_lines
        if "." in line and not line.startswith("goal:")
    )
    goal = parse_formula(goal_line.removeprefix("goal:").strip())
    proof_start = lines.index("<proof>", end_theorem)
    proof_end = lines.index("</proof>", proof_start)
    proof_lines: list[ProofLine] = []
    line_pattern = re.compile(r"(?P<number>\d+)\.\s+(?P<formula>.+?)\s+;\s+(?P<rule>\S+)(?P<tail>.*)")
    for raw in lines[proof_start + 1 : proof_end]:
        match = line_pattern.fullmatch(raw)
        if match is None:
            raise ValueError(f"invalid proof line: {raw!r}")
        tail = match.group("tail").strip().split()
        open_marker = tail.index("open") if "open" in tail else len(tail)
        references = tuple(int(value) for value in tail[:open_marker])
        open_assumptions = tuple(int(value) for value in tail[open_marker + 1 :])
        proof_lines.append(
            ProofLine(
                line_no=int(match.group("number")),
                formula=parse_formula(match.group("formula")),
                rule=match.group("rule"),
                references=references,
                open_assumptions=open_assumptions,
            )
        )
    return Proof(premises=premises, goal=goal, lines=tuple(proof_lines))
