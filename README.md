[![Tests](https://github.com/data-context-hq/datacontext/actions/workflows/tests.yml/badge.svg)](https://github.com/data-context-hq/datacontext/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/datacontext.svg)](https://pypi.org/project/datacontext/)
[![Python](https://img.shields.io/pypi/pyversions/datacontext.svg)](https://pypi.org/project/datacontext/)
[![License](https://img.shields.io/pypi/l/datacontext.svg)](https://github.com/data-context-hq/datacontext/blob/main/LICENSE)
[![Discussions](https://img.shields.io/badge/GitHub-Discussions-2ea44f)](https://github.com/data-context-hq/datacontext/discussions)
[![Roadmap](https://img.shields.io/badge/Roadmap-DataContext-blue)](https://github.com/data-context-hq/datacontext/blob/main/ROADMAP.md)
# DataContext
#### Runtime attribution for data access in Python

[Why](#why-datacontext) | [How It Works](#how-it-works) | [Quick Start](#quick-start) | [Event Shape](#event-shape) | [Production Behavior](#production-behavior) | [Roadmap](https://github.com/data-context-hq/datacontext/blob/main/ROADMAP.md)

DataContext helps developers answer a simple question:

> Which code path, request, job, or agent caused this query?

DataContext gives developers and platform teams more context for understanding data access patterns and improving how production services use databases and data platforms.

DataContext is early and intentionally small. The core event model is designed to stay stable, while integrations and APIs will evolve with real-world usage.

## Install

```bash
pip install datacontext
```

Optional OpenTelemetry support:

```bash
pip install "datacontext[otel]"
```

## Quick Start

Configure DataContext at an explicit data-access boundary:

```python
import datacontext

datacontext.configure(
    service_name="checkout-api",
    environment="production",
    instruments=[
        datacontext.instrument_function(
            target="app.db.execute",
            query_arg="query",
            db_system="postgres",
            client="internal-db-wrapper",
        )
    ],
)
```

After configuration, calls to `app.db.execute(...)` emit one completed query event when the function returns or raises.

Wrappers preserve return values and re-raise original exceptions unchanged. If DataContext fails, your application should not.

Emitted event:

```json
{
  "event_name": "datacontext.query",
  "timestamp": "2026-05-15T10:31:04.203Z",
  "started_at": "2026-05-15T10:31:04.182Z",
  "ended_at": "2026-05-15T10:31:04.203Z",
  "service_name": "checkout-api",
  "environment": "production",
  "db_system": "postgres",
  "client": "internal-db-wrapper",
  "query_fingerprint": "sha256:4f5b7f...",
  "query_text": "select * from orders where id = ?",
  "duration_ms": 21.4,
  "callsite": {
    "file": "checkout.py",
    "path": "/app/checkout.py",
    "line": 42,
    "function": "load_cart",
    "stack": "checkout:42 load_cart -> routes:88 post_checkout"
  },
  "status": "ok"
}
```

## Why DataContext?

Queries often lose their application context by the time they reach logs, traces, or the data platform itself.

That makes it hard to answer:

- Which request, job, or agent triggered this query?
- Which code path caused this unexpected load?
- Which actor, tenant, or session was involved?

DataContext connects query events to runtime context, source callsites, and OpenTelemetry trace context when available.

## How It Works

<p align="center">
  <img src="https://raw.githubusercontent.com/data-context-hq/datacontext/main/assets/datacontext-flow.svg" alt="DataContext query attribution flow" width="680">
</p>

## Supported Today

DataContext currently supports:

- manual query instrumentation with `trace_query(...)` and `capture_query(...)`,
- wrapping explicit data-access functions with `instrument_function(...)`,
- JSONL, callback, and OpenTelemetry-oriented sinks,
- correlating query events with runtime context and active OpenTelemetry spans.

It does not automatically instrument database drivers yet.

## Planned Integrations

The first integration priorities are SQLAlchemy guidance and Snowflake support exploration. Other database clients, ORMs, and data-platform libraries will be prioritized from real usage.

Use [GitHub Discussions](https://github.com/data-context-hq/datacontext/discussions) or [feature requests](https://github.com/data-context-hq/datacontext/issues/new?template=feature_or_integration_request.md) to share the library, data-access pattern, sync/async behavior, and event fields you need.

## Add Runtime Context

DataContext is most useful when queries are connected to runtime context:

```python
from datacontext import context

with context.use(
    operation="checkout",
    actor="user:123",
    request_id="req_abc",
    attributes={"tenant": "acme", "region": "us-east-1"},
):
    run_business_logic()
```

Any query captured inside the context includes that attribution.

## Event Shape

DataContext emits one final event per query, at finish or error time.

Every normal event includes:

- `event_name`, `timestamp`, `started_at`, `ended_at`,
- `service_name`, `environment`, `db_system`, `client`,
- `query_fingerprint`, `duration_ms`, `callsite`, and `status`.

The `timestamp` is the event finish time and matches `ended_at`. By default, events also include sanitized `query_text`; it can be disabled globally or per captured query. Optional fields are only present when DataContext can derive them or when the caller supplies them.

Example `datacontext.query` event:

```json
{
  "event_name": "datacontext.query",
  "timestamp": "2026-05-15T10:31:04.203Z",
  "started_at": "2026-05-15T10:31:04.182Z",
  "ended_at": "2026-05-15T10:31:04.203Z",
  "service_name": "checkout-api",
  "environment": "production",
  "db_system": "postgres",
  "client": "internal-db-wrapper",
  "query_fingerprint": "sha256:4f5b7f...",
  "query_text": "select * from orders where id = ?",
  "duration_ms": 21.4,
  "callsite": {
    "file": "checkout.py",
    "path": "/app/checkout.py",
    "line": 42,
    "function": "load_cart",
    "stack": "checkout:42 load_cart -> routes:88 post_checkout"
  },
  "status": "ok",
  "trace_id": "0af7651916cd43dd8448eb211c80319c",
  "span_id": "b7ad6b7169203331",
  "trace_flags": "01",
  "operation": "checkout",
  "actor": "user:123",
  "request_id": "req_abc",
  "job_id": "job_456",
  "session_id": "sess_789",
  "rows": 12,
  "db_name": "checkout",
  "db_host": "postgres.internal",
  "attributes": {
    "tenant": "acme",
    "region": "us-east-1"
  }
}
```

On errors, DataContext emits `status: "error"` and includes compact error metadata before re-raising the original exception.

```json
{
  "status": "error",
  "error": {
    "type": "ValueError",
    "message": "boom"
  }
}
```

## Production Behavior

DataContext is designed to sit on production data-access paths without changing application behavior:

- wrappers preserve return values and re-raise original exceptions,
- DataContext capture failures fall back to a minimal event,
- sink failures are logged and dropped,
- sanitized `query_text` is emitted by default, while raw SQL is explicit opt-in,
- OpenTelemetry trace context is used when present, but DataContext does not configure tracing or exporters.

## Schema Philosophy

DataContext uses a small, stable event shape on purpose.

The core schema answers the questions teams usually need first:

- what query shape ran,
- where it came from in code,
- which runtime context caused it,
- which trace or span it belongs to.

The schema is meant to work as JSON logs, warehouse rows, debugging artifacts, or observability events. Team-specific metadata belongs in `attributes`, so teams can extend events without changing the common attribution layer.

## Manual Instrumentation

The Quick Start approach is the recommended default: configure DataContext once and wrap your existing data-access function. When that does not fit, you can instrument directly at the call site with the lower-level APIs:

```python
with datacontext.trace_query(
    db_system="postgres",
    client="internal-db-wrapper",
    query=query,
):
    db.execute(query)
```

Use `capture_query(...)` when timing is already measured by your integration:

```python
datacontext.capture_query(
    db_system="postgres",
    client="internal-db-wrapper",
    query=query,
    started_at=started_at,
    ended_at=ended_at,
    duration_ms=duration_ms,
    status="ok",
    rows=12,
)
```

## Privacy and Query Text

DataContext emits `query_fingerprint` and sanitized `query_text` by default. Raw query text is not emitted unless you explicitly opt in.

To emit only the fingerprint without sanitized query text, disable query text:

```python
datacontext.configure(
    service_name="checkout-api",
    environment="production",
    include_query_text=False,
)
```

The sanitizer uses the same normalization as fingerprinting: it replaces string and numeric literals with `?`, normalizes whitespace, lowercases SQL, and compacts placeholder `IN (...)` lists.

To include exact raw SQL instead, use the explicit raw-query option:

```python
datacontext.capture_query(
    db_system="postgres",
    client="internal-db-wrapper",
    query=query,
    started_at=started_at,
    ended_at=ended_at,
    duration_ms=duration_ms,
    status="ok",
    include_raw_query_text=True,
)
```

## OpenTelemetry

DataContext uses OpenTelemetry context when it exists. It does not set up tracing, choose exporters, or replace your existing pipeline.

With an active span, DataContext adds `trace_id`, `span_id`, and `trace_flags` to emitted events. It can also attach compact `datacontext.*` attributes to the active span, including query fingerprint, status, duration, operation, and request ID.

## Sinks

The default sink writes JSON Lines to stdout. You can send events to a file, a callback, or an OpenTelemetry-oriented sink.

Configure a file sink:

```python
import datacontext
from datacontext.sinks import FileJsonlSink

datacontext.configure(
    service_name="checkout-api",
    environment="production",
    sink=FileJsonlSink("datacontext.jsonl"),
)
```

Configure a callback sink:

```python
from datacontext.sinks import CallbackSink

datacontext.configure(
    service_name="checkout-api",
    environment="production",
    sink=CallbackSink(lambda event: send_to_pipeline(event)),
)
```

Sink failures are dropped and logged. They should not block application work.

## Community

Use [GitHub Discussions](https://github.com/data-context-hq/datacontext/discussions) for questions, design feedback, and integration ideas.

Use [GitHub Issues](https://github.com/data-context-hq/datacontext/issues) for bugs and focused feature requests.

## License

Apache-2.0
