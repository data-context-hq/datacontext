# DataContext

Runtime attribution for data access in Python.

DataContext helps developers answer a simple question:

> Which code path, request, job, or agent caused this query?

DataContext gives humans and agents more context for understanding data access patterns and improving how applications use databases and data platforms.

DataContext is pre-1.0. The first goal is attribution, with a small API designed to evolve carefully as integrations mature.

## Why DataContext?

Queries often lose their application context by the time they reach logs, traces, or the data platform itself.

That makes it hard to answer:

- Which request, job, or agent triggered this query?
- Which code path caused this unexpected load?
- Which actor, tenant, or session was involved?

DataContext connects query events to runtime context, source callsites, and OpenTelemetry trace context when available.

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

## What Gets Emitted

DataContext emits one final event per query, at finish or error time.

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
  "attributes": {
    "tenant": "acme",
    "region": "us-east-1"
  }
}
```

On errors, DataContext emits `status: "error"` and includes compact error metadata before re-raising the original exception.

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

DataContext always emits `query_fingerprint` by default. Raw query text is not emitted unless you explicitly opt in.

To include normalized query shape text, opt in with DataContext's built-in sanitizer:

```python
datacontext.configure(
    service_name="checkout-api",
    environment="production",
    include_query_text=True,
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

## License

Apache-2.0
