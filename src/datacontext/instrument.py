from __future__ import annotations

import functools
import importlib
import inspect
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from datacontext.capture import capture_query
from datacontext.event import utc_now_iso


_DATACONTEXT_WRAPPED_ATTR = "__datacontext_wrapped__"


@dataclass(frozen=True)
class FunctionInstrument:
    target: str
    query_arg: str | int
    db_system: str
    client: str
    db_name: str | None = None
    db_host: str | None = None
    attributes: Mapping[str, Any] | None = None

    def apply(self) -> Callable[..., Any]:
        owner, attr_name = _resolve_owner_and_attr(self.target)
        original = getattr(owner, attr_name)
        if getattr(original, _DATACONTEXT_WRAPPED_ATTR, False):
            return original

        signature = inspect.signature(original)

        if inspect.iscoroutinefunction(original):

            @functools.wraps(original)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                query = _extract_query(signature, self.query_arg, args, kwargs)
                started_at = utc_now_iso()
                start = time.perf_counter()
                try:
                    result = await original(*args, **kwargs)
                except BaseException as exc:
                    _capture_from_wrapper(self, query, started_at, start, "error", exc)
                    raise
                _capture_from_wrapper(self, query, started_at, start, "ok")
                return result

            setattr(async_wrapper, _DATACONTEXT_WRAPPED_ATTR, True)
            setattr(owner, attr_name, async_wrapper)
            return async_wrapper

        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            query = _extract_query(signature, self.query_arg, args, kwargs)
            started_at = utc_now_iso()
            start = time.perf_counter()
            try:
                result = original(*args, **kwargs)
            except BaseException as exc:
                _capture_from_wrapper(self, query, started_at, start, "error", exc)
                raise
            _capture_from_wrapper(self, query, started_at, start, "ok")
            return result

        setattr(wrapper, _DATACONTEXT_WRAPPED_ATTR, True)
        setattr(owner, attr_name, wrapper)
        return wrapper


def instrument_function(
    *,
    target: str,
    query_arg: str | int,
    db_system: str,
    client: str,
    db_name: str | None = None,
    db_host: str | None = None,
    attributes: Mapping[str, Any] | None = None,
) -> FunctionInstrument:
    return FunctionInstrument(
        target=target,
        query_arg=query_arg,
        db_system=db_system,
        client=client,
        db_name=db_name,
        db_host=db_host,
        attributes=attributes,
    )


def _capture_from_wrapper(
    instrument: FunctionInstrument,
    query: Any,
    started_at: str,
    start: float,
    status: str,
    error: BaseException | None = None,
) -> None:
    ended_at = utc_now_iso()
    capture_query(
        db_system=instrument.db_system,
        client=instrument.client,
        query=query,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=(time.perf_counter() - start) * 1000,
        status=status,
        db_name=instrument.db_name,
        db_host=instrument.db_host,
        error=error,
        attributes=instrument.attributes,
    )


def _extract_query(
    signature: inspect.Signature,
    query_arg: str | int,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    try:
        if isinstance(query_arg, int):
            return args[query_arg]
        bound = signature.bind_partial(*args, **kwargs)
        return bound.arguments.get(query_arg)
    except Exception:
        return None


def _resolve_owner_and_attr(target: str) -> tuple[Any, str]:
    parts = target.split(".")
    if len(parts) < 2:
        raise ValueError("target must be a dotted path")

    last_error: Exception | None = None
    for index in range(len(parts) - 1, 0, -1):
        module_name = ".".join(parts[:index])
        attr_parts = parts[index:]
        try:
            obj: Any = importlib.import_module(module_name)
        except Exception as exc:
            last_error = exc
            continue
        for attr in attr_parts[:-1]:
            obj = getattr(obj, attr)
        return obj, attr_parts[-1]
    if last_error is not None:
        raise last_error
    raise ImportError(target)
