from __future__ import annotations

import logging
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Protocol

from datacontext.sinks.stdout_jsonl import StdoutJsonlSink


LOGGER = logging.getLogger("datacontext")
DEFAULT_SERVICE_NAME = "unknown-service"
DEFAULT_ENVIRONMENT = "unknown"


class Sink(Protocol):
    def emit(self, event: dict[str, Any]) -> None:
        ...


@dataclass(frozen=True)
class Config:
    service_name: str = DEFAULT_SERVICE_NAME
    environment: str = DEFAULT_ENVIRONMENT
    sink: Sink | None = None
    include_query_text: bool = True
    include_raw_query_text: bool = False


class Runtime:
    def __init__(self, config: Config | None = None) -> None:
        self._config = config if config is not None else Config(sink=StdoutJsonlSink())

    @property
    def config(self) -> Config:
        return self._config

    def configure(
        self,
        *,
        service_name: str | None = None,
        environment: str | None = None,
        instruments: Iterable[Any] | None = None,
        sink: Sink | None = None,
        include_query_text: bool = True,
        include_raw_query_text: bool = False,
    ) -> Config:
        if not service_name:
            warnings.warn(
                "datacontext service_name is not configured; using unknown-service",
                RuntimeWarning,
                stacklevel=3,
            )
        if not environment:
            warnings.warn(
                "datacontext environment is not configured; using unknown",
                RuntimeWarning,
                stacklevel=3,
            )

        self._config = Config(
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
        return self._config

    @contextmanager
    def configured(
        self,
        *,
        service_name: str | None = None,
        environment: str | None = None,
        instruments: Iterable[Any] | None = None,
        sink: Sink | None = None,
        include_query_text: bool = True,
        include_raw_query_text: bool = False,
    ) -> Iterator[Config]:
        previous = self._config
        try:
            yield self.configure(
                service_name=service_name,
                environment=environment,
                instruments=instruments,
                sink=sink,
                include_query_text=include_query_text,
                include_raw_query_text=include_raw_query_text,
            )
        finally:
            self._config = previous

    def reset(self) -> None:
        self._config = Config(sink=StdoutJsonlSink())

    def emit(self, event: dict[str, Any]) -> None:
        try:
            sink = self._config.sink
            if sink is not None:
                sink.emit(event)
        except Exception:
            LOGGER.exception("datacontext sink failed")


_runtime = Runtime()


def configure(
    *,
    service_name: str | None = None,
    environment: str | None = None,
    instruments: Iterable[Any] | None = None,
    sink: Sink | None = None,
    include_query_text: bool = True,
    include_raw_query_text: bool = False,
) -> Config:
    return _runtime.configure(
        service_name=service_name,
        environment=environment,
        instruments=instruments,
        sink=sink,
        include_query_text=include_query_text,
        include_raw_query_text=include_raw_query_text,
    )


@contextmanager
def configured(
    *,
    service_name: str | None = None,
    environment: str | None = None,
    instruments: Iterable[Any] | None = None,
    sink: Sink | None = None,
    include_query_text: bool = True,
    include_raw_query_text: bool = False,
) -> Iterator[Config]:
    with _runtime.configured(
        service_name=service_name,
        environment=environment,
        instruments=instruments,
        sink=sink,
        include_query_text=include_query_text,
        include_raw_query_text=include_raw_query_text,
    ) as config:
        yield config


def get_config() -> Config:
    return _runtime.config


def reset_config() -> None:
    _runtime.reset()


def emit_event(event: dict[str, Any]) -> None:
    _runtime.emit(event)
