from __future__ import annotations

import functools
import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Mapping

from datacontext.capture import capture_query
from datacontext.event import utc_now_iso


_INSTRUMENTED_ATTR = "_datacontext_postgres_instrumented"
_WRAPPED_ATTR = "_datacontext_postgres_wrapped"
_suppress_cursor_capture: ContextVar[bool] = ContextVar(
    "datacontext_postgres_suppress_cursor_capture",
    default=False,
)


@dataclass(frozen=True)
class PostgresInstrument:
    connection: Any
    client: str = "psycopg"
    db_name: str | None = None
    db_host: str | None = None
    attributes: Mapping[str, Any] | None = None

    def apply(self) -> Any:
        _ensure_postgres_dependency()
        if getattr(self.connection, _INSTRUMENTED_ATTR, False):
            return self.connection

        self._wrap_connection_execute()
        self._wrap_cursor_factory()
        try:
            setattr(self.connection, _INSTRUMENTED_ATTR, True)
        except Exception:
            pass
        return self.connection

    def _wrap_connection_execute(self) -> None:
        original = getattr(self.connection, "execute", None)
        if original is None or getattr(original, _WRAPPED_ATTR, False):
            return

        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            query = _extract_query(args, kwargs)
            started_at = utc_now_iso()
            start = time.perf_counter()
            token = _suppress_cursor_capture.set(True)
            try:
                result = original(*args, **kwargs)
            except BaseException as exc:
                self._capture(query, started_at, start, "error", error=exc)
                raise
            finally:
                _suppress_cursor_capture.reset(token)
            self._capture(query, started_at, start, "ok", rows=_rowcount(result))
            return result

        setattr(wrapper, _WRAPPED_ATTR, True)
        _setattr(self.connection, "execute", wrapper)

    def _wrap_cursor_factory(self) -> None:
        original = getattr(self.connection, "cursor", None)
        if original is None or getattr(original, _WRAPPED_ATTR, False):
            return

        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cursor = original(*args, **kwargs)
            self._instrument_cursor(cursor)
            return cursor

        setattr(wrapper, _WRAPPED_ATTR, True)
        _setattr(self.connection, "cursor", wrapper)

    def _instrument_cursor(self, cursor: Any) -> None:
        if getattr(cursor, _INSTRUMENTED_ATTR, False):
            return
        self._wrap_cursor_execute(cursor, "execute")
        self._wrap_cursor_execute(cursor, "executemany")
        try:
            setattr(cursor, _INSTRUMENTED_ATTR, True)
        except Exception:
            pass

    def _wrap_cursor_execute(self, cursor: Any, method_name: str) -> None:
        original = getattr(cursor, method_name, None)
        if original is None or getattr(original, _WRAPPED_ATTR, False):
            return

        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _suppress_cursor_capture.get():
                return original(*args, **kwargs)
            query = _extract_query(args, kwargs)
            started_at = utc_now_iso()
            start = time.perf_counter()
            try:
                result = original(*args, **kwargs)
            except BaseException as exc:
                self._capture(query, started_at, start, "error", error=exc)
                raise
            self._capture(
                query,
                started_at,
                start,
                "ok",
                rows=_rowcount(result) or _rowcount(cursor),
            )
            return result

        setattr(wrapper, _WRAPPED_ATTR, True)
        _setattr(cursor, method_name, wrapper)

    def _capture(
        self,
        query: Any,
        started_at: str,
        start: float,
        status: str,
        *,
        rows: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        try:
            capture_query(
                db_system="postgresql",
                client=self.client,
                query=query,
                started_at=started_at,
                ended_at=utc_now_iso(),
                duration_ms=(time.perf_counter() - start) * 1000,
                status=status,
                db_name=self.db_name or _db_name_from_connection(self.connection),
                db_host=self.db_host or _db_host_from_connection(self.connection),
                rows=rows,
                error=error,
                attributes=self.attributes,
            )
        except Exception:
            pass


def instrument_postgres(
    connection: Any,
    *,
    client: str = "psycopg",
    db_name: str | None = None,
    db_host: str | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> PostgresInstrument:
    return PostgresInstrument(
        connection=connection,
        client=client,
        db_name=db_name,
        db_host=db_host,
        attributes=attributes,
    )


def _ensure_postgres_dependency() -> None:
    try:
        import psycopg as _psycopg  # noqa: F401
    except ImportError:
        try:
            import psycopg2 as _psycopg2  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "PostgreSQL support requires the optional dependency. "
                'Install it with: pip install "datacontext[postgres]"'
            ) from exc


def _extract_query(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
    if "query" in kwargs:
        return kwargs["query"]
    if "statement" in kwargs:
        return kwargs["statement"]
    return args[0] if args else None


def _db_name_from_connection(connection: Any) -> str | None:
    info = getattr(connection, "info", None)
    for name in ("dbname", "database"):
        value = getattr(info, name, None)
        if value:
            return str(value)
    dsn_parameters = getattr(info, "dsn_parameters", None)
    if isinstance(dsn_parameters, Mapping):
        value = dsn_parameters.get("dbname") or dsn_parameters.get("database")
        return str(value) if value else None
    return None


def _db_host_from_connection(connection: Any) -> str | None:
    info = getattr(connection, "info", None)
    value = getattr(info, "host", None)
    if value:
        return str(value)
    dsn_parameters = getattr(info, "dsn_parameters", None)
    if isinstance(dsn_parameters, Mapping):
        value = dsn_parameters.get("host")
        return str(value) if value else None
    return None


def _rowcount(value: Any) -> int | None:
    rowcount = getattr(value, "rowcount", None)
    if isinstance(rowcount, int) and rowcount >= 0:
        return rowcount
    return None


def _setattr(target: Any, name: str, value: Any) -> None:
    try:
        setattr(target, name, value)
    except Exception:
        pass


__all__ = ["PostgresInstrument", "instrument_postgres"]
