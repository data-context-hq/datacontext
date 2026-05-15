from __future__ import annotations

import json
import sys
from typing import Any, Mapping, TextIO


class StdoutJsonlSink:
    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def emit(self, event: Mapping[str, Any]) -> None:
        stream = self._stream if self._stream is not None else sys.stdout
        stream.write(json.dumps(event, sort_keys=True, default=str) + "\n")
        stream.flush()

