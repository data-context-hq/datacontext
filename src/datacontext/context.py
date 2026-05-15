from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping


@dataclass(frozen=True)
class TraceContext:
    operation: str | None = None
    actor: str | None = None
    request_id: str | None = None
    job_id: str | None = None
    session_id: str | None = None
    attributes: Mapping[str, Any] = field(default_factory=dict)


_current_context: ContextVar[TraceContext] = ContextVar(
    "datacontext_context", default=TraceContext()
)


def current() -> TraceContext:
    return _current_context.get()


@contextmanager
def use(
    *,
    operation: str | None = None,
    actor: str | None = None,
    request_id: str | None = None,
    job_id: str | None = None,
    session_id: str | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[TraceContext]:
    previous = current()
    merged_attributes = dict(previous.attributes)
    if attributes:
        merged_attributes.update(attributes)
    next_context = TraceContext(
        operation=operation if operation is not None else previous.operation,
        actor=actor if actor is not None else previous.actor,
        request_id=request_id if request_id is not None else previous.request_id,
        job_id=job_id if job_id is not None else previous.job_id,
        session_id=session_id if session_id is not None else previous.session_id,
        attributes=merged_attributes,
    )
    token = _current_context.set(next_context)
    try:
        yield next_context
    finally:
        _current_context.reset(token)


def reset() -> None:
    _current_context.set(TraceContext())

