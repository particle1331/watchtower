"""Tests for watchtower.cli helpers — stdin/stdout UTF-8 handling."""


import io

from watchtower import cli

UNICODE_SAMPLE = "Box: ├── │ └──  Arrow: →  Dash: —  Bullet: •  Check: ✓  café"


class _FakeStdin:
    """Minimal stand-in exposing a binary ``buffer`` like ``sys.stdin``."""

    def __init__(self, raw: bytes) -> None:
        self.buffer = io.BytesIO(raw)


def test_read_stdin_decodes_utf8_regardless_of_locale(monkeypatch):
    # Bytes are UTF-8; decoding them as cp1252 (the old Windows default)
    # would mangle every non-ASCII glyph into mojibake. _read_stdin must
    # decode as UTF-8 from the raw buffer.
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(UNICODE_SAMPLE.encode("utf-8")))
    assert cli._read_stdin() == UNICODE_SAMPLE


def test_force_utf8_streams_is_idempotent_and_safe():
    # Should never raise, even when called repeatedly or when streams lack
    # a reconfigure method (guarded by getattr).
    cli._force_utf8_streams()
    cli._force_utf8_streams()
