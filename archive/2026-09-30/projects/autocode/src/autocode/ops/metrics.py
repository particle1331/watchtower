"""Minimal Prometheus exposition without imposing a metrics dependency."""

from __future__ import annotations

from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self.counters: defaultdict[str, int] = defaultdict(int)
        self.gauges: dict[str, float] = {}

    def inc(self, name: str, amount: int = 1) -> None:
        self.counters[name] += amount

    def set(self, name: str, value: float) -> None:
        self.gauges[name] = value

    def prometheus(self) -> str:
        lines = [f"{name} {value}" for name, value in sorted(self.counters.items())]
        lines.extend(f"{name} {value}" for name, value in sorted(self.gauges.items()))
        return "\n".join(lines) + ("\n" if lines else "")
