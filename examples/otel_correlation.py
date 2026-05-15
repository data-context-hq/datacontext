from __future__ import annotations

import datacontext


datacontext.configure(service_name="checkout-api", environment="development")

try:
    from opentelemetry import trace
except ImportError:
    trace = None


if trace is not None:
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("example"):
        with datacontext.trace_query(
            db_system="postgres",
            client="internal-db-wrapper",
            query="select 1",
        ):
            pass

