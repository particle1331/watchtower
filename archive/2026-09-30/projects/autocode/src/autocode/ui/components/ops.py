"""Operations view model for queue and connection status."""

from __future__ import annotations


def queue_summary(*, queued: int, running: int, dead: int) -> dict[str, int]:
    return {"queued": queued, "running": running, "dead": dead}
