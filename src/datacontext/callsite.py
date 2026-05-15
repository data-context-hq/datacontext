from __future__ import annotations

import inspect
import os
from typing import Any


_INTERNAL_MODULE_PREFIXES = ("datacontext",)
_MAX_STACK_FRAMES = 8


def get_callsite() -> dict[str, Any]:
    try:
        stack: list[dict[str, Any]] = []
        for frame in inspect.stack()[2:]:
            module = frame.frame.f_globals.get("__name__", "")
            if not str(module).startswith(_INTERNAL_MODULE_PREFIXES):
                frame_info = {
                    "file": os.path.basename(frame.filename),
                    "path": frame.filename,
                    "line": frame.lineno,
                    "function": frame.function,
                }
                stack.append(frame_info)
                if len(stack) >= _MAX_STACK_FRAMES:
                    break
        if stack:
            return {**stack[0], "stack": _format_stack(stack)}
    except Exception:
        pass
    return {}


def _format_stack(stack: list[dict[str, Any]]) -> str:
    return " -> ".join(
        f"{_format_filename(frame['file'])}:{frame['line']} {frame['function']}"
        for frame in stack
    )


def _format_filename(filename: str) -> str:
    if filename.endswith(".py"):
        return filename[:-3]
    return filename
