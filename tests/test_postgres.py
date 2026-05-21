from __future__ import annotations

import builtins
import sys
import types
from typing import Any

import pytest

import datacontext


class Info:
    dbname = "checkout"
    host = "postgres.internal"


class Cursor:
    def __init__(self) -> None:
        self.rowcount = 0
        self.statements: list[Any] = []
        self.fail = False

    def execute(self, query: Any, params: Any = None) -> "Cursor":
        self.statements.append((query, params))
        if self.fail:
            raise RuntimeError("db down")
        self.rowcount = 3
        return self

    def executemany(self, query: Any, params_seq: Any) -> "Cursor":
        self.statements.append((query, params_seq))
        self.rowcount = 4
        return self


class Connection:
    info = Info()

    def __init__(self) -> None:
        self.cursor_instance = Cursor()
        self.rowcount = 2

    def cursor(self) -> Cursor:
        return self.cursor_instance

    def execute(self, query: Any, params: Any = None) -> Cursor:
        cursor = Cursor()
        cursor.rowcount = self.rowcount
        return cursor


class ConnectionExecuteViaCursor(Connection):
    def execute(self, query: Any, params: Any = None) -> Cursor:
        return self.cursor().execute(query, params)


def install_psycopg_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "psycopg", types.ModuleType("psycopg"))


def test_postgres_instrument_wraps_connection_execute(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_psycopg_stub(monkeypatch)
    connection = Connection()

    result = datacontext.instrument_postgres(
        connection,
        attributes={"pool": "primary"},
    ).apply().execute("select * from orders where id = %s", [42])

    assert result.rowcount == 2
    assert len(events) == 1
    event = events[0]
    assert event["status"] == "ok"
    assert event["db_system"] == "postgresql"
    assert event["client"] == "psycopg"
    assert event["db_name"] == "checkout"
    assert event["db_host"] == "postgres.internal"
    assert event["rows"] == 2
    assert event["attributes"] == {"pool": "primary"}
    assert event["query_text"] == "select * from orders where id = %s"


def test_postgres_instrument_wraps_cursor_execute(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_psycopg_stub(monkeypatch)
    connection = Connection()
    datacontext.instrument_postgres(connection).apply()
    cursor = connection.cursor()

    returned = cursor.execute("select * from users where id = %s", [7])

    assert returned is cursor
    assert len(events) == 1
    assert events[0]["status"] == "ok"
    assert events[0]["rows"] == 3
    assert events[0]["query_text"] == "select * from users where id = %s"


def test_postgres_instrument_wraps_cursor_executemany(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_psycopg_stub(monkeypatch)
    connection = Connection()
    datacontext.instrument_postgres(connection).apply()

    connection.cursor().executemany(
        "insert into orders (id) values (%s)",
        [(1,), (2,)],
    )

    assert len(events) == 1
    assert events[0]["status"] == "ok"
    assert events[0]["rows"] == 4
    assert events[0]["query_text"] == "insert into orders (id) values (%s)"


def test_connection_execute_does_not_double_capture_when_it_uses_cursor(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_psycopg_stub(monkeypatch)
    connection = ConnectionExecuteViaCursor()
    datacontext.instrument_postgres(connection).apply()

    connection.execute("select * from orders where id = %s", [42])

    assert len(events) == 1
    assert events[0]["rows"] == 3


def test_postgres_instrument_emits_error_and_reraises(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_psycopg_stub(monkeypatch)
    connection = Connection()
    datacontext.instrument_postgres(connection, db_name="override").apply()
    cursor = connection.cursor()
    cursor.fail = True

    with pytest.raises(RuntimeError, match="db down"):
        cursor.execute("select 1")

    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["db_name"] == "override"
    assert events[0]["error"] == {"type": "RuntimeError", "message": "db down"}


def test_postgres_instrument_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_psycopg_stub(monkeypatch)
    connection = Connection()

    datacontext.instrument_postgres(connection).apply()
    datacontext.instrument_postgres(connection).apply()
    connection.cursor().execute("select 1")

    assert len(events) == 1


def test_postgres_optional_dependency_has_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def import_without_postgres(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in {"psycopg", "psycopg2"}:
            raise ImportError(f"No module named {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "psycopg", raising=False)
    monkeypatch.delitem(sys.modules, "psycopg2", raising=False)
    monkeypatch.setattr(builtins, "__import__", import_without_postgres)

    with pytest.raises(ImportError, match=r"datacontext\[postgres\]"):
        datacontext.instrument_postgres(Connection()).apply()


def test_postgres_public_exports_are_available() -> None:
    assert datacontext.PostgresInstrument is not None
    assert datacontext.instrument_postgres is not None
