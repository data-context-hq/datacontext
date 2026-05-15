from __future__ import annotations

from typing import Any, Mapping


def get_trace_context() -> dict[str, str]:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        span_context = span.get_span_context()
        if not span_context or not span_context.is_valid:
            return {}
        return {
            "trace_id": f"{span_context.trace_id:032x}",
            "span_id": f"{span_context.span_id:016x}",
            "trace_flags": f"{int(span_context.trace_flags):02x}",
        }
    except Exception:
        return {}


def enrich_active_span(event: Mapping[str, Any]) -> None:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        span_context = span.get_span_context()
        if not span_context or not span_context.is_valid:
            return
        for key in (
            "db_system",
            "client",
            "query_fingerprint",
            "duration_ms",
            "status",
            "operation",
            "request_id",
        ):
            value = event.get(key)
            if value is not None:
                span.set_attribute(f"datacontext.{key}", value)
    except Exception:
        return

