from __future__ import annotations

import functools
import time
from dataclasses import dataclass
from typing import Any, Mapping

from datacontext.capture import capture_query
from datacontext.event import utc_now_iso


_INSTRUMENTED_ATTR = "_datacontext_bigquery_instrumented"
_WRAPPED_ATTR = "_datacontext_bigquery_wrapped"
_CAPTURED_ATTR = "_datacontext_bigquery_captured"


@dataclass(frozen=True)
class BigQueryInstrument:
    client: Any
    db_name: str | None = None
    db_host: str | None = "bigquery.googleapis.com"
    attributes: Mapping[str, Any] | None = None
    labels: Mapping[str, str] | None = None
    job_id_prefix: str | None = None

    def apply(self) -> Any:
        try:
            from google.cloud import bigquery as _bigquery  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "BigQuery support requires the optional dependency. "
                'Install it with: pip install "datacontext[bigquery]"'
            ) from exc

        if getattr(self.client, _INSTRUMENTED_ATTR, False):
            return self.client

        self._wrap_query()
        self._wrap_query_and_wait()
        try:
            setattr(self.client, _INSTRUMENTED_ATTR, True)
        except Exception:
            pass
        return self.client

    def _wrap_query(self) -> None:
        original = getattr(self.client, "query", None)
        if original is None or getattr(original, _WRAPPED_ATTR, False):
            return

        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            query = _extract_query(args, kwargs)
            kwargs = _apply_query_options(
                args,
                kwargs,
                labels=self.labels,
                job_id_prefix=self.job_id_prefix,
            )
            started_at = utc_now_iso()
            start = time.perf_counter()
            try:
                job = original(*args, **kwargs)
            except BaseException as exc:
                self._capture(query, started_at, start, "error", exc)
                raise
            self._wrap_job_result(job, query, started_at, start)
            return job

        setattr(wrapper, _WRAPPED_ATTR, True)
        setattr(self.client, "query", wrapper)

    def _wrap_query_and_wait(self) -> None:
        original = getattr(self.client, "query_and_wait", None)
        if original is None or getattr(original, _WRAPPED_ATTR, False):
            return

        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            query = _extract_query(args, kwargs)
            kwargs = _apply_query_and_wait_options(args, kwargs, labels=self.labels)
            started_at = utc_now_iso()
            start = time.perf_counter()
            try:
                result = original(*args, **kwargs)
            except BaseException as exc:
                self._capture(query, started_at, start, "error", exc)
                raise
            self._capture(query, started_at, start, "ok", rows=_rows_from_result(result))
            return result

        setattr(wrapper, _WRAPPED_ATTR, True)
        setattr(self.client, "query_and_wait", wrapper)

    def _wrap_job_result(
        self,
        job: Any,
        query: Any,
        started_at: str,
        start: float,
    ) -> None:
        original = getattr(job, "result", None)
        if original is None or getattr(original, _WRAPPED_ATTR, False):
            return

        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                result = original(*args, **kwargs)
            except BaseException as exc:
                if not _already_captured(job):
                    self._capture(
                        query,
                        started_at,
                        start,
                        "error",
                        exc,
                        job=job,
                    )
                raise
            if not _already_captured(job):
                self._capture(
                    query,
                    started_at,
                    start,
                    "ok",
                    job=job,
                    rows=_rows_from_result(result) or _rows_from_job(job),
                )
            return result

        setattr(wrapper, _WRAPPED_ATTR, True)
        setattr(job, "result", wrapper)

    def _capture(
        self,
        query: Any,
        started_at: str,
        start: float,
        status: str,
        error: BaseException | None = None,
        *,
        job: Any = None,
        rows: int | None = None,
    ) -> None:
        if job is not None:
            _mark_captured(job)
        try:
            capture_query(
                db_system="bigquery",
                client="google-cloud-bigquery",
                query=query,
                started_at=started_at,
                ended_at=utc_now_iso(),
                duration_ms=(time.perf_counter() - start) * 1000,
                status=status,
                db_name=self.db_name or _project_from_client(self.client),
                db_host=self.db_host,
                rows=rows,
                error=error,
                attributes=_combined_attributes(self.attributes, job),
            )
        except Exception:
            pass


def instrument_bigquery(
    client: Any,
    *,
    db_name: str | None = None,
    db_host: str | None = "bigquery.googleapis.com",
    attributes: Mapping[str, Any] | None = None,
    labels: Mapping[str, str] | None = None,
    job_id_prefix: str | None = None,
) -> BigQueryInstrument:
    return BigQueryInstrument(
        client=client,
        db_name=db_name,
        db_host=db_host,
        attributes=attributes,
        labels=labels,
        job_id_prefix=job_id_prefix,
    )


def _extract_query(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
    if "query" in kwargs:
        return kwargs["query"]
    return args[0] if args else None


def _apply_query_options(
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    *,
    labels: Mapping[str, str] | None,
    job_id_prefix: str | None,
) -> dict[str, Any]:
    updated = dict(kwargs)
    _apply_labels(args, updated, labels=labels)
    if job_id_prefix and not _query_job_id_passed(args, updated):
        updated["job_id_prefix"] = job_id_prefix
    return updated


def _apply_query_and_wait_options(
    args: tuple[Any, ...],
    kwargs: Mapping[str, Any],
    *,
    labels: Mapping[str, str] | None,
) -> dict[str, Any]:
    updated = dict(kwargs)
    _apply_labels(args, updated, labels=labels)
    return updated


def _apply_labels(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    labels: Mapping[str, str] | None,
) -> None:
    if not labels:
        return
    job_config = _job_config_from_call(args, kwargs)
    if job_config is not None:
        _merge_labels(job_config, labels)
        return
    try:
        from google.cloud import bigquery

        job_config = bigquery.QueryJobConfig(labels=dict(labels))
    except Exception:
        return
    kwargs["job_config"] = job_config


def _job_config_from_call(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> Any:
    if "job_config" in kwargs:
        return kwargs["job_config"]
    if len(args) > 1:
        return args[1]
    return None


def _merge_labels(job_config: Any, labels: Mapping[str, str]) -> None:
    try:
        existing = getattr(job_config, "labels", None) or {}
        setattr(job_config, "labels", {**dict(labels), **dict(existing)})
    except Exception:
        pass


def _query_job_id_passed(args: tuple[Any, ...], kwargs: Mapping[str, Any]) -> bool:
    return len(args) > 2 or "job_id" in kwargs or "job_id_prefix" in kwargs


def _project_from_client(client: Any) -> str | None:
    project = getattr(client, "project", None)
    return str(project) if project else None


def _rows_from_result(result: Any) -> int | None:
    return _non_negative_int(getattr(result, "total_rows", None))


def _rows_from_job(job: Any) -> int | None:
    return _non_negative_int(getattr(job, "num_dml_affected_rows", None))


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _combined_attributes(
    attributes: Mapping[str, Any] | None,
    job: Any,
) -> Mapping[str, Any] | None:
    combined = dict(attributes or {})
    if job is not None:
        _put_attr(combined, "bigquery.job_id", getattr(job, "job_id", None))
        _put_attr(combined, "bigquery.location", getattr(job, "location", None))
        _put_attr(
            combined,
            "bigquery.total_bytes_processed",
            getattr(job, "total_bytes_processed", None),
        )
        destination = getattr(job, "destination", None)
        if destination is not None:
            _put_attr(combined, "bigquery.destination", str(destination))
    return combined or None


def _put_attr(attributes: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        attributes[key] = value


def _already_captured(job: Any) -> bool:
    return bool(getattr(job, _CAPTURED_ATTR, False))


def _mark_captured(job: Any) -> None:
    try:
        setattr(job, _CAPTURED_ATTR, True)
    except Exception:
        pass


__all__ = ["BigQueryInstrument", "instrument_bigquery"]
