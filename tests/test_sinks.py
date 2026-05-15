from __future__ import annotations

import io
import json

from datacontext.sinks import CallbackSink, FileJsonlSink, OTelSink, StdoutJsonlSink


def test_stdout_jsonl_sink_writes_event() -> None:
    stream = io.StringIO()
    StdoutJsonlSink(stream=stream).emit({"b": 2, "a": 1})

    assert json.loads(stream.getvalue()) == {"a": 1, "b": 2}


def test_file_jsonl_sink_writes_event(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    FileJsonlSink(path).emit({"event_name": "datacontext.query"})

    assert json.loads(path.read_text()) == {"event_name": "datacontext.query"}


def test_callback_sink_calls_callback() -> None:
    events = []
    CallbackSink(events.append).emit({"event_name": "datacontext.query"})

    assert events == [{"event_name": "datacontext.query"}]


def test_otel_sink_is_public_and_safe_without_provider() -> None:
    OTelSink().emit({"event_name": "datacontext.query"})
