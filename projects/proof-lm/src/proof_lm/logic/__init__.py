"""Small, independently checked propositional proof domain."""

from .formula import Formula, atom, bottom, conjunction, disjunction, implication, negation
from .generator import GeneratedExample, generate_examples
from .parser import parse_formula, parse_proof
from .proofs import Proof, ProofLine, VerificationResult, render_proof, verify_proof
from .semantics import entails, find_countermodel, truth_table

__all__ = [
    "Formula",
    "GeneratedExample",
    "Proof",
    "ProofLine",
    "VerificationResult",
    "atom",
    "bottom",
    "conjunction",
    "disjunction",
    "entails",
    "find_countermodel",
    "generate_examples",
    "implication",
    "negation",
    "parse_formula",
    "parse_proof",
    "render_proof",
    "truth_table",
    "verify_proof",
]
