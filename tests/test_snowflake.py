from __future__ import annotations

import builtins
from typing import Any

import pytest

import datacontext


class Connection:
    account = "acme-prod"
    warehouse = "analytics_wh"
    role = "loader"
    schema = "public"


def cursor_class() -> type[Any]:
    class Cursor:
        sfqid: str | None = None
        rowcount = -1
        connection = Connection()

        def execute(self, command: str, *args: Any, **kwargs: Any) -> Any:
            self.sfqid = "01b123"
            self.rowcount = 7
            return self

        def executemany(self, command: str, seqparams: Any, *args: Any, **kwargs: Any) -> Any:
            self.sfqid = "01b124"
            self.rowcount = len(seqparams)
            return self

        def execute_async(self, command: str, *args: Any, **kwargs: Any) -> dict[str, str]:
            self.sfqid = "01b125"
            self.rowcount = -1
            return {"queryId": self.sfqid}

    return Cursor


def test_snowflake_optional_dependency_has_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def import_without_snowflake(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("snowflake"):
            raise ImportError("No module named snowflake")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_snowflake)

    with pytest.raises(ImportError, match=r"datacontext\[snowflake\]"):
        datacontext.instrument_snowflake().apply()


def test_snowflake_instrument_wraps_once() -> None:
    Cursor = cursor_class()
    original = Cursor.execute

    target = datacontext.instrument_snowflake(cursor_class=Cursor).apply()
    first_wrapped = Cursor.execute
    datacontext.instrument_snowflake(cursor_class=Cursor).apply()

    assert target is Cursor
    assert Cursor.execute is first_wrapped
    assert Cursor.execute is not original


def test_snowflake_execute_success_emits_event(events: list[dict]) -> None:
    Cursor = cursor_class()
    datacontext.instrument_snowflake(
        cursor_class=Cursor,
        attributes={"pipeline": "daily"},
    ).apply()
    cursor = Cursor()

    result = cursor.execute("select * from orders where id = 42")

    assert result is cursor
    assert len(events) == 1
    event = events[0]
    assert event["status"] == "ok"
    assert event["db_system"] == "snowflake"
    assert event["client"] == "snowflake-connector-python"
    assert event["rows"] == 7
    assert event["query_text"] == "select * from orders where id = ?"
    assert event["attributes"] == {
        "pipeline": "daily",
        "snowflake.query_id": "01b123",
        "snowflake.account": "acme-prod",
        "snowflake.warehouse": "analytics_wh",
        "snowflake.role": "loader",
        "snowflake.schema": "public",
    }


def test_snowflake_execute_error_emits_event_and_reraises(
    events: list[dict],
) -> None:
    class Cursor:
        sfqid = "01b126"
        rowcount = -1
        connection = Connection()

        def execute(self, command: str) -> Any:
            raise RuntimeError("snowflake down")

    datacontext.instrument_snowflake(cursor_class=Cursor).apply()

    with pytest.raises(RuntimeError, match="snowflake down"):
        Cursor().execute("select 1")

    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert "rows" not in events[0]
    assert events[0]["attributes"]["snowflake.query_id"] == "01b126"
    assert events[0]["error"] == {"type": "RuntimeError", "message": "snowflake down"}


def test_snowflake_executemany_captures_command_and_row_count(
    events: list[dict],
) -> None:
    Cursor = cursor_class()
    datacontext.instrument_snowflake(cursor_class=Cursor).apply()

    Cursor().executemany("insert into orders values (?)", [(1,), (2,)])

    assert len(events) == 1
    assert events[0]["query_text"] == "insert into orders values (?)"
    assert events[0]["rows"] == 2
    assert events[0]["attributes"]["snowflake.query_id"] == "01b124"


def test_snowflake_execute_async_captures_submission_event_and_sfqid(
    events: list[dict],
) -> None:
    Cursor = cursor_class()
    datacontext.instrument_snowflake(cursor_class=Cursor).apply()

    result = Cursor().execute_async("select count(*) from orders")

    assert result == {"queryId": "01b125"}
    assert len(events) == 1
    assert events[0]["status"] == "ok"
    assert "rows" not in events[0]
    assert events[0]["attributes"]["snowflake.query_id"] == "01b125"


def test_snowflake_metadata_uses_private_connection_attributes(
    events: list[dict],
) -> None:
    class PrivateConnection:
        _account = "private-account"
        _warehouse = "private-wh"
        _role = "private-role"
        _schema = "private-schema"

    class Cursor:
        sfqid = "01b127"
        rowcount = 1
        _connection = PrivateConnection()

        def execute(self, command: str) -> Any:
            return self

    datacontext.instrument_snowflake(cursor_class=Cursor).apply()

    Cursor().execute("select 1")

    assert events[0]["attributes"] == {
        "snowflake.query_id": "01b127",
        "snowflake.account": "private-account",
        "snowflake.warehouse": "private-wh",
        "snowflake.role": "private-role",
        "snowflake.schema": "private-schema",
    }


def test_snowflake_query_text_privacy_settings_apply(events: list[dict]) -> None:
    datacontext.configure(
        service_name="svc",
        environment="test",
        sink=type("Sink", (), {"emit": lambda self, event: events.append(dict(event))})(),
        include_query_text=False,
    )
    Cursor = cursor_class()
    datacontext.instrument_snowflake(cursor_class=Cursor).apply()

    Cursor().execute("select * from users where email = 'a@example.com'")

    assert len(events) == 1
    assert "query_text" not in events[0]
