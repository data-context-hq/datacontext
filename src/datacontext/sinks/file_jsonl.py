from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class FileJsonlSink:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def emit(self, event: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, sort_keys=True, default=str) + "\n")

