"""WebSocket adapter contract; replay semantics live in autocode.realtime."""

from autocode.realtime import FanoutHub


class LiveRun:
    def __init__(self) -> None:
        self.hub = FanoutHub()

    def emit(self, kind: str, payload: dict[str, object]) -> int:
        return self.hub.publish(kind, payload).cursor
