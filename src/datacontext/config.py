from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Any, Iterable, Protocol

from datacontext.sinks.stdout_jsonl import StdoutJsonlSink


LOGGER = logging.getLogger("datacontext")
DEFAULT_SERVICE_NAME = "unknown-service"
DEFAULT_ENVIRONMENT = "unknown"


class Sink(Protocol):
    def emit(self, event: dict[str, Any]) -> None:
        ...


@dataclass
class Config:
    service_name: str = DEFAULT_SERVICE_NAME
    environment: str = DEFAULT_ENVIRONMENT
    sink: Sink | None = None
    include_query_text: bool = False
    include_raw_query_text: bool = False


_config = Config(sink=StdoutJsonlSink())


def configure(
    *,
    service_name: str | None = None,
    environment: str | None = None,
    instruments: Iterable[Any] | None = None,
    sink: Sink | None = None,
    include_query_text: bool = False,
    include_raw_query_text: bool = False,
) -> Config:
    global _config
    if not service_name:
        warnings.warn(
            "datacontext service_name is not configured; using unknown-service",
            RuntimeWarning,
            stacklevel=2,
        )
    if not environment:
        warnings.warn(
            "datacontext environment is not configured; using unknown",
            RuntimeWarning,
            stacklevel=2,
        )

    _config = Config(
        service_name=service_name or DEFAULT_SERVICE_NAME,
        environment=environment or DEFAULT_ENVIRONMENT,
        sink=sink if sink is not None else StdoutJsonlSink(),
        include_query_text=include_query_text,
        include_raw_query_text=include_raw_query_text,
    )

    if instruments:
        for instrument in instruments:
            try:
                instrument.apply()
            except Exception:
                LOGGER.exception("datacontext instrument failed")
    return _config


def get_config() -> Config:
    return _config


def reset_config() -> None:
    global _config
    _config = Config(sink=StdoutJsonlSink())


def emit_event(event: dict[str, Any]) -> None:
    try:
        sink = _config.sink
        if sink is not None:
            sink.emit(event)
    except Exception:
        LOGGER.exception("datacontext sink failed")
