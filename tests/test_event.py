from __future__ import annotations

from datacontext.event import build_query_event
from datacontext.callsite import get_callsite


def test_build_query_event_required_fields() -> None:
    event = build_query_event(
        service_name="svc",
        environment="prod",
        db_system="postgres",
        client="client",
        query="select 1",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        status="ok",
        callsite={"file": "app.py", "line": 1},
    )

    assert event == {
        "event_name": "datacontext.query",
        "timestamp": "2026-01-01T00:00:01Z",
        "started_at": "2026-01-01T00:00:00Z",
        "ended_at": "2026-01-01T00:00:01Z",
        "service_name": "svc",
        "environment": "prod",
        "db_system": "postgres",
        "client": "client",
        "query_fingerprint": event["query_fingerprint"],
        "duration_ms": 1000,
        "callsite": {"file": "app.py", "line": 1},
        "status": "ok",
    }


def test_callsite_includes_bounded_stack() -> None:
    callsite = _call_get_callsite()

    assert callsite["function"] == "test_callsite_includes_bounded_stack"
    assert callsite["stack"].startswith("test_event:")
    assert " test_callsite_includes_bounded_stack" in callsite["stack"]
    assert callsite["stack"].count(" -> ") < 8


def _call_get_callsite() -> dict:
    return get_callsite()
