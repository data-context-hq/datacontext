from __future__ import annotations

import builtins
import sys
import types
from typing import Any

import pytest

import datacontext


class EventRegistry:
    def __init__(self) -> None:
        self.listeners: dict[tuple[Any, str], list[Any]] = {}

    def listen(self, target: Any, name: str, fn: Any) -> None:
        self.listeners.setdefault((target, name), []).append(fn)


class Url:
    drivername = "postgresql+psycopg"
    database = "checkout"
    host = "postgres.internal"


class Engine:
    url = Url()


class Cursor:
    rowcount = 3


def install_sqlalchemy_stub(monkeypatch: pytest.MonkeyPatch) -> EventRegistry:
    registry = EventRegistry()
    module = types.ModuleType("sqlalchemy")
    module.event = registry
    monkeypatch.setitem(sys.modules, "sqlalchemy", module)
    return registry


def test_sqlalchemy_instrument_registers_engine_listeners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = install_sqlalchemy_stub(monkeypatch)
    engine = Engine()

    target = datacontext.instrument_sqlalchemy(engine).apply()

    assert target is engine
    assert len(registry.listeners[(engine, "before_cursor_execute")]) == 1
    assert len(registry.listeners[(engine, "after_cursor_execute")]) == 1
    assert len(registry.listeners[(engine, "handle_error")]) == 1


def test_sqlalchemy_instrument_emits_success_event(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    registry = install_sqlalchemy_stub(monkeypatch)
    engine = Engine()
    context = types.SimpleNamespace()
    instrument = datacontext.instrument_sqlalchemy(engine, attributes={"pool": "main"})
    instrument.apply()

    registry.listeners[(engine, "before_cursor_execute")][0](
        object(),
        Cursor(),
        "select * from orders where id = 42",
        {},
        context,
        False,
    )
    registry.listeners[(engine, "after_cursor_execute")][0](
        object(),
        Cursor(),
        "select * from orders where id = 42",
        {},
        context,
        False,
    )

    assert len(events) == 1
    event = events[0]
    assert event["status"] == "ok"
    assert event["client"] == "sqlalchemy"
    assert event["db_system"] == "postgresql+psycopg"
    assert event["db_name"] == "checkout"
    assert event["db_host"] == "postgres.internal"
    assert event["rows"] == 3
    assert event["attributes"] == {"pool": "main"}
    assert event["query_text"] == "select * from orders where id = ?"


def test_sqlalchemy_instrument_emits_error_event(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    registry = install_sqlalchemy_stub(monkeypatch)
    engine = Engine()
    context = types.SimpleNamespace(statement="select 1")
    error = RuntimeError("db down")
    datacontext.instrument_sqlalchemy(engine, db_system="postgres").apply()

    registry.listeners[(engine, "before_cursor_execute")][0](
        object(), Cursor(), "select 1", {}, context, False
    )
    registry.listeners[(engine, "handle_error")][0](
        types.SimpleNamespace(
            connection=object(),
            cursor=Cursor(),
            execution_context=context,
            original_exception=error,
            statement=None,
        )
    )

    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["db_system"] == "postgres"
    assert events[0]["error"] == {"type": "RuntimeError", "message": "db down"}


def test_sqlalchemy_instrument_uses_async_engine_sync_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = install_sqlalchemy_stub(monkeypatch)
    sync_engine = Engine()
    async_engine = types.SimpleNamespace(sync_engine=sync_engine, url=sync_engine.url)

    target = datacontext.instrument_sqlalchemy(async_engine).apply()

    assert target is sync_engine
    assert (sync_engine, "before_cursor_execute") in registry.listeners


def test_sqlalchemy_optional_dependency_has_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def import_without_sqlalchemy(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "sqlalchemy":
            raise ImportError("No module named sqlalchemy")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_sqlalchemy)

    with pytest.raises(ImportError, match=r"datacontext\[sqlalchemy\]"):
        datacontext.instrument_sqlalchemy(Engine()).apply()
