from __future__ import annotations

import pytest

import datacontext
from datacontext import context


def test_trace_query_emits_completed_event_on_success(events: list[dict]) -> None:
    with datacontext.trace_query(db_system="postgres", client="client", query="select 1"):
        pass

    assert len(events) == 1
    event = events[0]
    assert event["event_name"] == "datacontext.query"
    assert event["status"] == "ok"
    assert event["service_name"] == "svc"
    assert event["environment"] == "test"
    assert event["db_system"] == "postgres"
    assert event["client"] == "client"
    assert event["duration_ms"] >= 0
    assert "started_at" in event
    assert "ended_at" in event


def test_trace_query_emits_error_and_reraises(events: list[dict]) -> None:
    error = ValueError("boom")

    with pytest.raises(ValueError) as raised:
        with datacontext.trace_query(db_system="postgres", client="client", query="select 1"):
            raise error

    assert raised.value is error
    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error"] == {"type": "ValueError", "message": "boom"}


def test_capture_query_includes_context_and_attributes(events: list[dict]) -> None:
    with context.use(
        operation="checkout",
        actor="user:123",
        request_id="req",
        job_id="job",
        session_id="sess",
        attributes={"tenant": "acme"},
    ):
        datacontext.capture_query(
            db_system="postgres",
            client="client",
            query="select * from users where email = 'private@example.com'",
            started_at="2026-01-01T00:00:00Z",
            ended_at="2026-01-01T00:00:01Z",
            duration_ms=1000,
            status="ok",
            rows=2,
            attributes={"region": "us"},
        )

    event = events[0]
    assert event["operation"] == "checkout"
    assert event["actor"] == "user:123"
    assert event["request_id"] == "req"
    assert event["job_id"] == "job"
    assert event["session_id"] == "sess"
    assert event["rows"] == 2
    assert event["attributes"] == {"tenant": "acme", "region": "us"}


def test_sanitized_query_text_is_emitted_by_default(events: list[dict]) -> None:
    query = "select * from users where email = 'private@example.com'"

    datacontext.capture_query(
        db_system="postgres",
        client="client",
        query=query,
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        status="ok",
    )

    event_text = str(events[0])
    assert "private@example.com" not in event_text
    assert events[0]["query_text"] == "select * from users where email = ?"
    assert "query_fingerprint" in events[0]


def test_sanitized_query_text_can_be_disabled_by_config(events: list[dict]) -> None:
    datacontext.configure(
        service_name="svc",
        environment="test",
        sink=type("Sink", (), {"emit": lambda self, event: events.append(dict(event))})(),
        include_query_text=False,
    )

    datacontext.capture_query(
        db_system="postgres",
        client="client",
        query="select * from users where email = 'private@example.com' and id = 42",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        status="ok",
    )

    assert "query_text" not in events[0]
    assert "private@example.com" not in str(events[0])


def test_raw_query_text_can_be_emitted_per_call(events: list[dict]) -> None:
    query = "select * from users where email = 'private@example.com'"

    datacontext.capture_query(
        db_system="postgres",
        client="client",
        query=query,
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        status="ok",
        include_raw_query_text=True,
    )

    assert events[0]["query_text"] == query


def test_missing_service_metadata_warns_and_uses_defaults() -> None:
    with pytest.warns(RuntimeWarning) as warnings:
        config = datacontext.configure()

    messages = [str(item.message) for item in warnings]
    assert any("service_name" in message for message in messages)
    assert any("environment" in message for message in messages)
    assert config.service_name == "unknown-service"
    assert config.environment == "unknown"


def test_sink_failures_do_not_affect_application_code() -> None:
    class BrokenSink:
        def emit(self, event: dict) -> None:
            raise RuntimeError("sink down")

    datacontext.configure(service_name="svc", environment="test", sink=BrokenSink())

    with datacontext.trace_query(db_system="postgres", client="client", query="select 1"):
        pass
