from __future__ import annotations

import functools
import importlib
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from datacontext.capture import capture_query
from datacontext.event import utc_now_iso


_INSTRUMENTED_ATTR = "_datacontext_snowflake_instrumented"


@dataclass(frozen=True)
class SnowflakeInstrument:
    cursor_class: Any | None = None
    client: str = "snowflake-connector-python"
    attributes: Mapping[str, Any] | None = None

    def apply(self) -> Any:
        cursor_class = self.cursor_class or _snowflake_cursor_class()
        if getattr(cursor_class, _INSTRUMENTED_ATTR, False):
            return cursor_class

        for method_name in ("execute", "executemany", "execute_async"):
            original = getattr(cursor_class, method_name, None)
            if callable(original):
                setattr(cursor_class, method_name, self._wrap(original))

        try:
            setattr(cursor_class, _INSTRUMENTED_ATTR, True)
        except Exception:
            pass
        return cursor_class

    def _wrap(self, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapper(cursor: Any, *args: Any, **kwargs: Any) -> Any:
            query = _query_from_args(args, kwargs)
            started_at = utc_now_iso()
            start = time.perf_counter()
            try:
                result = original(cursor, *args, **kwargs)
            except BaseException as exc:
                self._capture(cursor, query, started_at, start, "error", exc)
                raise
            self._capture(cursor, query, started_at, start, "ok")
            return result

        return wrapper

    def _capture(
        self,
        cursor: Any,
        query: Any,
        started_at: str,
        start: float,
        status: str,
        error: BaseException | None = None,
    ) -> None:
        try:
            capture_query(
                db_system="snowflake",
                client=self.client,
                query=query,
                started_at=started_at,
                ended_at=utc_now_iso(),
                duration_ms=(time.perf_counter() - start) * 1000,
                status=status,
                rows=_rowcount(cursor),
                error=error,
                attributes=_attributes(cursor, self.attributes),
            )
        except Exception:
            pass


def instrument_snowflake(
    *,
    cursor_class: Any | None = None,
    client: str = "snowflake-connector-python",
    attributes: Mapping[str, Any] | None = None,
) -> SnowflakeInstrument:
    return SnowflakeInstrument(
        cursor_class=cursor_class,
        client=client,
        attributes=attributes,
    )


def _snowflake_cursor_class() -> Any:
    try:
        module = importlib.import_module("snowflake.connector.cursor")
    except ImportError as exc:
        raise ImportError(
            "Snowflake support requires the optional dependency. "
            'Install it with: pip install "datacontext[snowflake]"'
        ) from exc
    return module.SnowflakeCursor


def _query_from_args(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
    if args:
        return args[0]
    for key in ("command", "sql", "query"):
        if key in kwargs:
            return kwargs[key]
    return None


def _attributes(
    cursor: Any,
    configured_attributes: Mapping[str, Any] | None,
) -> dict[str, Any]:
    attributes = dict(configured_attributes or {})

    sfqid = getattr(cursor, "sfqid", None)
    if sfqid:
        attributes["snowflake.query_id"] = str(sfqid)

    connection = _connection_from_cursor(cursor)
    for attribute_name, source_names in {
        "snowflake.account": ("account", "_account"),
        "snowflake.warehouse": ("warehouse", "_warehouse"),
        "snowflake.role": ("role", "_role"),
        "snowflake.schema": ("schema", "_schema"),
    }.items():
        value = _first_attr(cursor, source_names)
        if value is None:
            value = _first_attr(connection, source_names)
        if value is not None:
            attributes[attribute_name] = str(value)

    return attributes


def _connection_from_cursor(cursor: Any) -> Any:
    connection = _first_attr(cursor, ("connection", "_connection"))
    if callable(connection):
        try:
            return connection()
        except Exception:
            return None
    return connection


def _first_attr(obj: Any, names: tuple[str, ...]) -> Any:
    if obj is None:
        return None
    for name in names:
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if value is not None:
            return value
    return None


def _rowcount(cursor: Any) -> int | None:
    rowcount = getattr(cursor, "rowcount", None)
    if isinstance(rowcount, int) and rowcount >= 0:
        return rowcount
    return None
