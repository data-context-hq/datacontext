from __future__ import annotations

import builtins
import sys
import types
from typing import Any

import pytest

import datacontext


class RowIterator:
    total_rows = 7


class QueryJobConfig:
    def __init__(self, *, labels: dict[str, str] | None = None) -> None:
        self.labels = labels


class QueryJob:
    job_id = "job-123"
    location = "US"
    total_bytes_processed = 42
    destination = "project.dataset.table"
    num_dml_affected_rows = 3

    def __init__(self, *, error: BaseException | None = None) -> None:
        self.error = error
        self.result_calls = 0

    def result(self) -> RowIterator:
        self.result_calls += 1
        if self.error is not None:
            raise self.error
        return RowIterator()


class Client:
    project = "analytics-prod"

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.calls: list[dict[str, Any]] = []
        self.next_error: BaseException | None = None

    def query(
        self,
        query: str,
        job_config: QueryJobConfig | None = None,
        job_id: str | None = None,
        job_id_prefix: str | None = None,
    ) -> QueryJob:
        self.queries.append(query)
        self.calls.append(
            {
                "method": "query",
                "job_config": job_config,
                "job_id": job_id,
                "job_id_prefix": job_id_prefix,
            }
        )
        return QueryJob(error=self.next_error)

    def query_and_wait(
        self,
        query: str,
        *,
        job_config: QueryJobConfig | None = None,
    ) -> RowIterator:
        self.queries.append(query)
        self.calls.append(
            {
                "method": "query_and_wait",
                "job_config": job_config,
            }
        )
        if self.next_error is not None:
            raise self.next_error
        return RowIterator()


def install_bigquery_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    google = types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    bigquery = types.ModuleType("google.cloud.bigquery")
    bigquery.QueryJobConfig = QueryJobConfig
    cloud.bigquery = bigquery
    google.cloud = cloud
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.cloud", cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", bigquery)


def test_bigquery_query_captures_when_job_result_completes(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_bigquery_stub(monkeypatch)
    client = Client()
    datacontext.instrument_bigquery(client, attributes={"team": "platform"}).apply()

    job = client.query("select * from dataset.orders where id = 42")

    assert events == []
    assert job.result().total_rows == 7
    assert len(events) == 1
    event = events[0]
    assert event["status"] == "ok"
    assert event["client"] == "google-cloud-bigquery"
    assert event["db_system"] == "bigquery"
    assert event["db_name"] == "analytics-prod"
    assert event["db_host"] == "bigquery.googleapis.com"
    assert event["rows"] == 7
    assert event["query_text"] == "select * from dataset.orders where id = ?"
    assert event["attributes"] == {
        "team": "platform",
        "bigquery.job_id": "job-123",
        "bigquery.location": "US",
        "bigquery.total_bytes_processed": 42,
        "bigquery.destination": "project.dataset.table",
    }


def test_bigquery_query_captures_result_error(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_bigquery_stub(monkeypatch)
    client = Client()
    client.next_error = RuntimeError("permission denied")
    datacontext.instrument_bigquery(client).apply()

    job = client.query("select 1")
    with pytest.raises(RuntimeError, match="permission denied"):
        job.result()

    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error"] == {
        "type": "RuntimeError",
        "message": "permission denied",
    }


def test_bigquery_query_and_wait_captures_immediately(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_bigquery_stub(monkeypatch)
    client = Client()
    datacontext.instrument_bigquery(client, db_name="override-project").apply()

    result = client.query_and_wait(query="select count(*) from dataset.orders")

    assert result.total_rows == 7
    assert len(events) == 1
    assert events[0]["status"] == "ok"
    assert events[0]["db_name"] == "override-project"
    assert events[0]["rows"] == 7


def test_bigquery_query_and_wait_captures_error(
    monkeypatch: pytest.MonkeyPatch,
    events: list[dict],
) -> None:
    install_bigquery_stub(monkeypatch)
    client = Client()
    client.next_error = RuntimeError("quota exceeded")
    datacontext.instrument_bigquery(client).apply()

    with pytest.raises(RuntimeError, match="quota exceeded"):
        client.query_and_wait("select 1")

    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error"] == {
        "type": "RuntimeError",
        "message": "quota exceeded",
    }


def test_bigquery_injects_labels_and_job_id_prefix_when_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_bigquery_stub(monkeypatch)
    client = Client()
    datacontext.instrument_bigquery(
        client,
        labels={"service": "checkout", "env": "test"},
        job_id_prefix="dc_",
    ).apply()

    client.query("select 1")
    client.query_and_wait("select 2")

    query_call = client.calls[0]
    assert query_call["job_config"].labels == {
        "service": "checkout",
        "env": "test",
    }
    assert query_call["job_id_prefix"] == "dc_"

    query_and_wait_call = client.calls[1]
    assert query_and_wait_call["job_config"].labels == {
        "service": "checkout",
        "env": "test",
    }


def test_bigquery_merges_labels_without_overriding_explicit_job_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_bigquery_stub(monkeypatch)
    client = Client()
    explicit_config = QueryJobConfig(labels={"service": "manual", "manual": "true"})
    datacontext.instrument_bigquery(
        client,
        labels={"service": "checkout", "env": "test"},
        job_id_prefix="dc_",
    ).apply()

    client.query(
        "select 1",
        job_config=explicit_config,
        job_id="manual-job",
        job_id_prefix="manual_",
    )
    client.query_and_wait("select 2", job_config=explicit_config)

    query_call = client.calls[0]
    assert query_call["job_config"] is explicit_config
    assert query_call["job_config"].labels == {
        "service": "manual",
        "env": "test",
        "manual": "true",
    }
    assert query_call["job_id"] == "manual-job"
    assert query_call["job_id_prefix"] == "manual_"

    query_and_wait_call = client.calls[1]
    assert query_and_wait_call["job_config"] is explicit_config
    assert query_and_wait_call["job_config"].labels == {
        "service": "manual",
        "env": "test",
        "manual": "true",
    }


def test_bigquery_merges_labels_into_positional_job_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_bigquery_stub(monkeypatch)
    client = Client()
    explicit_config = QueryJobConfig(labels={"env": "manual"})
    datacontext.instrument_bigquery(
        client,
        labels={"service": "checkout", "env": "test"},
    ).apply()

    client.query("select 1", explicit_config)

    query_call = client.calls[0]
    assert query_call["job_config"] is explicit_config
    assert query_call["job_config"].labels == {
        "service": "checkout",
        "env": "manual",
    }


def test_bigquery_optional_dependency_has_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def import_without_bigquery(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "google.cloud":
            raise ImportError("No module named google.cloud")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_bigquery)

    with pytest.raises(ImportError, match=r"datacontext\[bigquery\]"):
        datacontext.instrument_bigquery(Client()).apply()
