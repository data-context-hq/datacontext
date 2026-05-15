from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from datacontext import context
from datacontext.callsite import get_callsite
from datacontext.fingerprint import fingerprint_query, normalize_query
from datacontext.otel import enrich_active_span, get_trace_context


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_query_event(
    *,
    service_name: str,
    environment: str,
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
    callsite: Mapping[str, Any] | None = None,
    include_query_text: bool = False,
    include_raw_query_text: bool = False,
) -> dict[str, Any]:
    trace_context = context.current()
    event: dict[str, Any] = {
        "event_name": "datacontext.query",
        "timestamp": ended_at,
        "started_at": started_at,
        "ended_at": ended_at,
        "service_name": service_name,
        "environment": environment,
        "db_system": db_system,
        "client": client,
        "query_fingerprint": fingerprint_query(query),
        "duration_ms": duration_ms,
        "callsite": dict(callsite) if callsite is not None else get_callsite(),
        "status": status,
    }
    event.update(get_trace_context())

    if include_raw_query_text:
        try:
            event["query_text"] = str(query)
        except Exception:
            pass
    elif include_query_text:
        try:
            event["query_text"] = normalize_query(query)
        except Exception:
            pass

    for key in ("operation", "actor", "request_id", "job_id", "session_id"):
        value = getattr(trace_context, key)
        if value is not None:
            event[key] = value

    combined_attributes = dict(trace_context.attributes)
    if attributes:
        combined_attributes.update(attributes)
    if combined_attributes:
        event["attributes"] = combined_attributes

    optional_values = {
        "db_name": db_name,
        "db_host": db_host,
        "rows": rows,
    }
    for key, value in optional_values.items():
        if value is not None:
            event[key] = value

    if error is not None:
        event["error"] = _format_error(error)

    enrich_active_span(event)
    return event


def _format_error(error: BaseException | str) -> dict[str, str]:
    if isinstance(error, BaseException):
        return {
            "type": type(error).__name__,
            "message": str(error),
        }
    return {"type": "Error", "message": str(error)}
