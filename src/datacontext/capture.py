from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping

from datacontext.config import emit_event, get_config
from datacontext.event import build_query_event, utc_now_iso


@contextmanager
def trace_query(
    *,
    db_system: str,
    client: str,
    query: Any,
    db_name: str | None = None,
    db_host: str | None = None,
    attributes: Mapping[str, Any] | None = None,
    include_query_text: bool | None = None,
    include_raw_query_text: bool | None = None,
) -> Iterator[None]:
    started_at = utc_now_iso()
    start = time.perf_counter()
    try:
        yield
    except BaseException as exc:
        ended_at = utc_now_iso()
        duration_ms = (time.perf_counter() - start) * 1000
        capture_query(
            db_system=db_system,
            client=client,
            query=query,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            status="error",
            db_name=db_name,
            db_host=db_host,
            error=exc,
            attributes=attributes,
            include_query_text=include_query_text,
            include_raw_query_text=include_raw_query_text,
        )
        raise
    else:
        ended_at = utc_now_iso()
        duration_ms = (time.perf_counter() - start) * 1000
        capture_query(
            db_system=db_system,
            client=client,
            query=query,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            status="ok",
            db_name=db_name,
            db_host=db_host,
            attributes=attributes,
            include_query_text=include_query_text,
            include_raw_query_text=include_raw_query_text,
        )


def capture_query(
    *,
    db_system: str,
    client: str,
    query: Any,
    started_at: str,
    ended_at: str,
    duration_ms: float,
    status: str,
    db_name: str | None = None,
    db_host: str | None = None,
    rows: int | None = None,
    error: BaseException | str | None = None,
    attributes: Mapping[str, Any] | None = None,
    include_query_text: bool | None = None,
    include_raw_query_text: bool | None = None,
) -> dict[str, Any]:
    config = get_config()
    should_include_query_text = (
        config.include_query_text if include_query_text is None else include_query_text
    )
    should_include_raw_query_text = (
        config.include_raw_query_text
        if include_raw_query_text is None
        else include_raw_query_text
    )
    try:
        event = build_query_event(
            service_name=config.service_name,
            environment=config.environment,
            db_system=db_system,
            client=client,
            query=query,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            status=status,
            db_name=db_name,
            db_host=db_host,
            rows=rows,
            error=error,
            attributes=attributes,
            include_query_text=should_include_query_text,
            include_raw_query_text=should_include_raw_query_text,
        )
    except Exception:
        event = {
            "event_name": "datacontext.query",
            "timestamp": ended_at,
            "started_at": started_at,
            "ended_at": ended_at,
            "service_name": config.service_name,
            "environment": config.environment,
            "db_system": db_system,
            "client": client,
            "query_fingerprint": "unknown",
            "duration_ms": duration_ms,
            "callsite": {},
            "status": status,
        }
    emit_event(event)
    return event
