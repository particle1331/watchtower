"""Explicit merge policy for replicated sessions."""

from __future__ import annotations

from dataclasses import replace

from autocode.domain import SessionRecord, merge_append_only_events


def merge_records(left: SessionRecord, right: SessionRecord) -> SessionRecord:
    """Merge scalars by deterministic LWW and events by set union.

    The event ID tie-break makes the operation commutative, associative, and
    idempotent, which are the properties a two-device sync loop needs.
    """

    newest = max((left, right), key=lambda record: (record.updated_at, record.session_id))
    events = merge_append_only_events(left.events, right.events)
    return replace(newest, version=len(events), events=events)
