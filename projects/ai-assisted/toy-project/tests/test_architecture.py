"""Architecture test (ADR-004): the dependency rule in ARCHITECTURE.md, checked with ast.

Every .py file under habits/ is parsed. Each import must follow the layer table and the
standard-library allowlist of the file's layer. The allowlists are written out here because
Python 3.9 has no sys.stdlib_module_names.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path
from typing import List, Optional, Sequence

HABITS_DIR = Path(__file__).resolve().parent.parent / "habits"
PACKAGE = "habits"

ROOT_LAYER = "<package root>"  # modules directly under habits/, such as __init__.py
COMPOSITION_ROOT_FILES = {("main.py",), ("__main__.py",)}  # may import anything; not checked

# Habits layers each layer may import (ARCHITECTURE.md). Same-layer imports are always allowed.
ALLOWED_INTERNAL = {
    ROOT_LAYER: set(),
    "domain": {"domain"},
    "application": {"domain", "application"},
    "adapters": {"domain", "application", "adapters"},
    "cli": {"application", "domain", "cli"},
}

PURE_STDLIB = {
    "__future__", "collections", "dataclasses", "datetime", "enum", "functools", "typing",
}

# Standard-library modules each layer may import. Any other external module is a violation.
STDLIB_ALLOWLIST = {
    ROOT_LAYER: PURE_STDLIB,
    "domain": PURE_STDLIB,
    "application": PURE_STDLIB,
    "adapters": PURE_STDLIB | {"os", "sqlite3", "tempfile"},
    # argparse parses arguments; sys supplies the default output streams. Nothing else.
    "cli": PURE_STDLIB | {"argparse", "json", "sys"},
}


def layer_of(rel_parts: Sequence[str]) -> str:
    """Return the layer for a path relative to habits/, such as ("domain", "habit.py")."""
    return rel_parts[0] if len(rel_parts) > 1 else ROOT_LAYER


def find_violations(source: str, rel_parts: Sequence[str]) -> List[str]:
    """Return one message for each import in source that breaks the rule for habits/<rel_parts>."""
    if tuple(rel_parts) in COMPOSITION_ROOT_FILES:
        return []
    where = "/".join(rel_parts)
    layer = layer_of(rel_parts)
    if layer not in ALLOWED_INTERNAL:
        return [f"{where}: layer '{layer}' is not in the architecture table"]
    package = [PACKAGE, *rel_parts[:-1]]
    violations = []
    for node in ast.walk(ast.parse(source, filename=where)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = _absolute_module(node, package)
            if module is None:
                violations.append(f"{where}:{node.lineno}: relative import climbs above habits")
                continue
            # "from habits import adapters" reaches a layer through the package name.
            if module == PACKAGE:
                names = [f"{PACKAGE}.{alias.name}" for alias in node.names]
            else:
                names = [module]
        else:
            continue
        for name in names:
            reason = _reason(name, layer)
            if reason:
                violations.append(f"{where}:{node.lineno}: import {name}: {reason}")
    return violations


def _absolute_module(node: ast.ImportFrom, package: Sequence[str]) -> Optional[str]:
    """Return the absolute module of a from-import, or None if it climbs above habits."""
    if node.level == 0:
        return node.module
    keep = len(package) - (node.level - 1)
    if keep < 1:
        return None
    parts = list(package[:keep])
    if node.module:
        parts.append(node.module)
    return ".".join(parts)


def _reason(name: str, layer: str) -> Optional[str]:
    """Return why importing name breaks the rule for layer, or None if the import is allowed."""
    parts = name.split(".")
    if parts[0] != PACKAGE:
        if parts[0] in STDLIB_ALLOWLIST[layer]:
            return None
        return f"'{parts[0]}' is not on the {layer} standard-library allowlist"
    if len(parts) == 1 or parts[1] in ALLOWED_INTERNAL[layer]:
        return None
    return f"{layer} may not import habits.{parts[1]}"


CLOCK_ATTRIBUTES = {"today", "now", "utcnow"}  # date.today, datetime.now, datetime.utcnow
CLOCK_EXEMPT_FILES = {("main.py",)}  # the composition root only; __main__.py is NOT exempt


def find_clock_reads(source: str, rel_parts: Sequence[str]) -> List[str]:
    """Return one message per reference to a clock attribute, outside the composition root.

    Flags attribute access, not only calls, so an alias such as `f = datetime.now` is caught.
    Dynamic access (getattr with a computed name) is not detected; see the whitepaper.
    ADR-003: dates are injected.
    """
    if tuple(rel_parts) in CLOCK_EXEMPT_FILES:
        return []
    where = "/".join(rel_parts)
    reads = []
    for node in ast.walk(ast.parse(source, filename=where)):
        if isinstance(node, ast.Attribute) and node.attr in CLOCK_ATTRIBUTES:
            reads.append(f"{where}:{node.lineno}: reads the clock via .{node.attr}")
    return reads


def habits_source_files() -> List[Path]:
    return sorted(HABITS_DIR.rglob("*.py"))


class DependencyRuleTests(unittest.TestCase):
    def test_habits_package_follows_the_dependency_rule(self):
        violations = []
        for path in habits_source_files():
            source = path.read_text(encoding="utf-8")
            violations += find_violations(source, path.relative_to(HABITS_DIR).parts)
        self.assertEqual(violations, [])

    def test_domain_application_and_adapters_are_all_scanned(self):
        # Guards against a vacuous pass, for example if HABITS_DIR pointed at the wrong folder.
        layers = {layer_of(path.relative_to(HABITS_DIR).parts) for path in habits_source_files()}
        self.assertTrue({"domain", "application", "adapters"} <= layers)


class ClockRuleTests(unittest.TestCase):
    def test_only_the_composition_root_reads_the_clock(self):
        reads = []
        for path in habits_source_files():
            source = path.read_text(encoding="utf-8")
            reads += find_clock_reads(source, path.relative_to(HABITS_DIR).parts)
        self.assertEqual(reads, [])

    def test_clock_checker_flags_a_domain_call(self):
        reads = find_clock_reads("import datetime\nTODAY = datetime.date.today()\n", ("domain", "streaks.py"))
        self.assertEqual(len(reads), 1)

    def test_clock_checker_flags_an_alias_without_a_call(self):
        reads = find_clock_reads("import datetime\nnow = datetime.datetime.now\n", ("domain", "habit.py"))
        self.assertEqual(len(reads), 1)

    def test_clock_checker_does_not_exempt_dunder_main(self):
        reads = find_clock_reads("import datetime\nd = datetime.date.today()\n", ("__main__.py",))
        self.assertEqual(len(reads), 1)

    def test_clock_checker_allows_the_composition_root(self):
        self.assertEqual(find_clock_reads("import datetime\nd = datetime.date.today()\n", ("main.py",)), [])


class CheckerSelfTests(unittest.TestCase):
    """The checker must be seen to fail, or a clean run of the rule above proves nothing."""

    def test_reports_a_cross_layer_import(self):
        snippet = "from habits.adapters.memory_repository import InMemoryHabitRepository\n"
        violations = find_violations(snippet, ("application", "use_cases.py"))
        self.assertEqual(len(violations), 1)
        self.assertIn("application may not import habits.adapters", violations[0])

    def test_reports_a_layer_reached_through_the_package_name(self):
        violations = find_violations("from habits import cli\n", ("adapters", "store.py"))
        self.assertEqual(len(violations), 1)

    def test_reports_a_relative_import_into_another_layer(self):
        snippet = "from ..adapters import memory_repository\n"
        violations = find_violations(snippet, ("application", "use_cases.py"))
        self.assertEqual(len(violations), 1)

    def test_reports_a_relative_import_that_climbs_above_habits(self):
        violations = find_violations("from ... import errors\n", ("domain", "habit.py"))
        self.assertEqual(len(violations), 1)

    def test_reports_a_standard_library_module_outside_the_allowlist(self):
        violations = find_violations("import json\n", ("domain", "export.py"))
        self.assertEqual(len(violations), 1)

    def test_reports_a_file_in_an_unknown_layer(self):
        violations = find_violations("x = 1\n", ("plugins", "extra.py"))
        self.assertEqual(len(violations), 1)

    def test_accepts_imports_that_follow_the_rule(self):
        snippet = (
            "import datetime\n"
            "from habits.domain.errors import DomainError\n"
            "from .errors import DomainError as Local\n"
        )
        self.assertEqual(find_violations(snippet, ("domain", "habit.py")), [])

    def test_adapters_may_use_sqlite_but_domain_may_not(self):
        adapter = find_violations("import sqlite3\n", ("adapters", "sqlite_repository.py"))
        domain = find_violations("import sqlite3\n", ("domain", "habit.py"))
        self.assertEqual(adapter, [])
        self.assertEqual(len(domain), 1)

    def test_composition_root_may_import_anything(self):
        snippet = (
            "from habits.adapters.sqlite_repository import SqliteHabitRepository\n"
            "import requests\n"
        )
        self.assertEqual(find_violations(snippet, ("main.py",)), [])
