from __future__ import annotations

from typing import Any, Mapping


class OTelSink:
    """A minimal optional sink that attaches the final event to the active span."""

    def emit(self, event: Mapping[str, Any]) -> None:
        from datacontext.otel import enrich_active_span

        enrich_active_span(event)

