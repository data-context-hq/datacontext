from __future__ import annotations

import pytest

import datacontext


def test_otel_absent_is_safe(events: list[dict]) -> None:
    with datacontext.trace_query(db_system="postgres", client="client", query="select 1"):
        pass

    assert len(events) == 1


def test_otel_context_is_included_when_available(events: list[dict]) -> None:
    trace = pytest.importorskip("opentelemetry.trace")

    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("span"):
        with datacontext.trace_query(db_system="postgres", client="client", query="select 1"):
            pass

    event = events[0]
    if "trace_id" not in event:
        pytest.skip("No active OpenTelemetry provider produced a valid span context")
    assert len(event["trace_id"]) == 32
    assert len(event["span_id"]) == 16
    assert "trace_flags" in event

