from __future__ import annotations

from typing import Any, Callable, Mapping


class CallbackSink:
    def __init__(self, callback: Callable[[Mapping[str, Any]], None]) -> None:
        self.callback = callback

    def emit(self, event: Mapping[str, Any]) -> None:
        self.callback(event)

