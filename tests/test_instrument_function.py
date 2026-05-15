from __future__ import annotations

import importlib
import asyncio
import sys

import pytest

import datacontext


def test_sync_function_instrumentation_emits_event(tmp_path, events: list[dict]) -> None:
    module_path = tmp_path / "sampledb.py"
    module_path.write_text(
        "def execute(query):\n"
        "    return 'result:' + query\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module("sampledb")
        datacontext.instrument_function(
            target="sampledb.execute",
            query_arg="query",
            db_system="postgres",
            client="wrapper",
        ).apply()

        assert module.execute("select 1") == "result:select 1"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("sampledb", None)

    assert len(events) == 1
    assert events[0]["status"] == "ok"
    assert events[0]["db_system"] == "postgres"


def test_async_function_instrumentation_emits_event(tmp_path, events: list[dict]) -> None:
    module_path = tmp_path / "asyncdb.py"
    module_path.write_text(
        "async def execute(query):\n"
        "    return 'result:' + query\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module("asyncdb")
        datacontext.instrument_function(
            target="asyncdb.execute",
            query_arg=0,
            db_system="postgres",
            client="wrapper",
        ).apply()

        assert asyncio.run(module.execute("select 1")) == "result:select 1"
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("asyncdb", None)

    assert len(events) == 1
    assert events[0]["status"] == "ok"


def test_function_instrumentation_reraises_original_exception(
    tmp_path, events: list[dict]
) -> None:
    module_path = tmp_path / "errordb.py"
    module_path.write_text(
        "def execute(query):\n"
        "    raise ValueError('bad query')\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module("errordb")
        datacontext.instrument_function(
            target="errordb.execute",
            query_arg="query",
            db_system="postgres",
            client="wrapper",
        ).apply()

        with pytest.raises(ValueError, match="bad query"):
            module.execute("select 1")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("errordb", None)

    assert len(events) == 1
    assert events[0]["status"] == "error"


def test_function_instrumentation_is_idempotent(tmp_path, events: list[dict]) -> None:
    module_path = tmp_path / "idempotentdb.py"
    module_path.write_text(
        "def execute(query):\n"
        "    return query\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(tmp_path))
    try:
        module = importlib.import_module("idempotentdb")
        instrument = datacontext.instrument_function(
            target="idempotentdb.execute",
            query_arg="query",
            db_system="postgres",
            client="wrapper",
        )
        first = instrument.apply()
        second = instrument.apply()

        assert first is second
        module.execute("select 1")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("idempotentdb", None)

    assert len(events) == 1
