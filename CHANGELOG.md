# Changelog

All notable changes to DataContext will be documented in this file.

## 0.1.0

Initial public release.

- Added runtime query attribution events.
- Added manual query capture with `trace_query(...)` and `capture_query(...)`.
- Added function wrapping with `instrument_function(...)`.
- Added runtime context propagation for operation, actor, request, job, session, and attributes.
- Added query fingerprinting with sanitized query text emitted by default and raw query text available by explicit opt-in.
- Added stdout JSONL, file JSONL, callback, and OpenTelemetry-oriented sinks.
- Added OpenTelemetry trace context correlation when available.
- Added dbt execution context attribution through the optional `dbt` extra.
