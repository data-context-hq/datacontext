from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

from datacontext.capture import capture_query
from datacontext.event import utc_now_iso


_STARTED_AT_ATTR = "_datacontext_started_at"
_START_TIME_ATTR = "_datacontext_start_time"
_INSTRUMENTED_ATTR = "_datacontext_sqlalchemy_instrumented"


@dataclass(frozen=True)
class SQLAlchemyInstrument:
    engine: Any
    db_system: str | None = None
    client: str = "sqlalchemy"
    db_name: str | None = None
    db_host: str | None = None
    attributes: Mapping[str, Any] | None = None

    def apply(self) -> Any:
        try:
            from sqlalchemy import event
        except ImportError as exc:
            raise ImportError(
                "SQLAlchemy support requires the optional dependency. "
                'Install it with: pip install "datacontext[sqlalchemy]"'
            ) from exc

        target = _event_target(self.engine)
        if getattr(target, _INSTRUMENTED_ATTR, False):
            return target

        event.listen(target, "before_cursor_execute", self._before_cursor_execute)
        event.listen(target, "after_cursor_execute", self._after_cursor_execute)
        event.listen(target, "handle_error", self._handle_error)
        try:
            setattr(target, _INSTRUMENTED_ATTR, True)
        except Exception:
            pass
        return target

    def _before_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        try:
            setattr(context, _STARTED_AT_ATTR, utc_now_iso())
            setattr(context, _START_TIME_ATTR, time.perf_counter())
        except Exception:
            pass

    def _after_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        self._capture(conn, cursor, statement, context, "ok")

    def _handle_error(self, exception_context: Any) -> None:
        execution_context = getattr(exception_context, "execution_context", None)
        statement = getattr(exception_context, "statement", None)
        if statement is None and execution_context is not None:
            statement = getattr(execution_context, "statement", None)
        self._capture(
            getattr(exception_context, "connection", None),
            getattr(exception_context, "cursor", None),
            statement,
            execution_context,
            "error",
            getattr(exception_context, "original_exception", None),
        )

    def _capture(
        self,
        conn: Any,
        cursor: Any,
        statement: Any,
        context: Any,
        status: str,
        error: BaseException | None = None,
    ) -> None:
        try:
            started_at = getattr(context, _STARTED_AT_ATTR, None) or utc_now_iso()
            started = getattr(context, _START_TIME_ATTR, None)
            duration_ms = (
                (time.perf_counter() - started) * 1000
                if isinstance(started, float)
                else 0.0
            )
            capture_query(
                db_system=self.db_system or _db_system_from_engine(self.engine),
                client=self.client,
                query=statement,
                started_at=started_at,
                ended_at=utc_now_iso(),
                duration_ms=duration_ms,
                status=status,
                db_name=self.db_name or _db_name_from_engine(self.engine),
                db_host=self.db_host or _db_host_from_engine(self.engine),
                rows=_rowcount(cursor),
                error=error,
                attributes=self.attributes,
            )
        except Exception:
            pass


def instrument_sqlalchemy(
    engine: Any,
    *,
    db_system: str | None = None,
    client: str = "sqlalchemy",
    db_name: str | None = None,
    db_host: str | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> SQLAlchemyInstrument:
    return SQLAlchemyInstrument(
        engine=engine,
        db_system=db_system,
        client=client,
        db_name=db_name,
        db_host=db_host,
        attributes=attributes,
    )


def _event_target(engine: Any) -> Any:
    return getattr(engine, "sync_engine", engine)


def _db_system_from_engine(engine: Any) -> str:
    url = getattr(engine, "url", None)
    return str(getattr(url, "drivername", None) or getattr(url, "name", None) or "unknown")


def _db_name_from_engine(engine: Any) -> str | None:
    url = getattr(engine, "url", None)
    database = getattr(url, "database", None)
    return str(database) if database else None


def _db_host_from_engine(engine: Any) -> str | None:
    url = getattr(engine, "url", None)
    host = getattr(url, "host", None)
    return str(host) if host else None


def _rowcount(cursor: Any) -> int | None:
    rowcount = getattr(cursor, "rowcount", None)
    if isinstance(rowcount, int) and rowcount >= 0:
        return rowcount
    return None
