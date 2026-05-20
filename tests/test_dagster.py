from __future__ import annotations

import builtins
from types import SimpleNamespace
from typing import Any

import pytest

import datacontext
from datacontext import context
from datacontext import dagster as dagster_module


class AssetKey:
    def __init__(self, *path: str) -> None:
        self.path = list(path)

    def to_user_string(self) -> str:
        return "/".join(self.path)


class RaisingAssetContext:
    run_id = "run-op"
    job_name = "daily_job"
    op_name = "load_orders"

    @property
    def asset_key(self) -> Any:
        raise RuntimeError("asset key is not available")


def emit_query() -> dict[str, Any]:
    return datacontext.capture_query(
        db_system="postgres",
        client="client",
        query="select * from orders where id = 1",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        status="ok",
    )


def test_asset_context_metadata_extraction(events: list[dict]) -> None:
    dagster_context = SimpleNamespace(
        run_id="run-123",
        job_name="asset_job",
        op_name="orders_op",
        asset_key=AssetKey("warehouse", "orders"),
    )

    with datacontext.use_dagster_context(dagster_context):
        emit_query()

    event = events[0]
    assert event["job_id"] == "run-123"
    assert event["operation"] == "warehouse/orders"
    assert event["attributes"] == {
        "dagster.run_id": "run-123",
        "dagster.job_name": "asset_job",
        "dagster.op_name": "orders_op",
        "dagster.asset_key": "warehouse/orders",
    }


def test_op_only_context_metadata_extraction(events: list[dict]) -> None:
    dagster_context = RaisingAssetContext()

    with datacontext.use_dagster_context(dagster_context):
        emit_query()

    event = events[0]
    assert event["job_id"] == "run-op"
    assert event["operation"] == "load_orders"
    assert event["attributes"] == {
        "dagster.run_id": "run-op",
        "dagster.job_name": "daily_job",
        "dagster.op_name": "load_orders",
    }


def test_partition_key_extraction(events: list[dict]) -> None:
    dagster_context = SimpleNamespace(
        run_id="run-partitioned",
        job_name="partitioned_job",
        op_name="orders_op",
        asset_key=AssetKey("orders"),
        partition_key="2026-01-01",
    )

    with datacontext.use_dagster_context(dagster_context):
        emit_query()

    assert events[0]["attributes"]["dagster.partition_key"] == "2026-01-01"


def test_nested_datacontext_context_restoration(events: list[dict]) -> None:
    dagster_context = SimpleNamespace(
        run_id="run-inner",
        job_name="asset_job",
        op_name="orders_op",
        asset_key=AssetKey("orders"),
    )

    with context.use(operation="outer", job_id="outer-job", attributes={"tenant": "acme"}):
        with datacontext.use_dagster_context(dagster_context):
            inner = context.current()
            assert inner.operation == "orders"
            assert inner.job_id == "run-inner"
            assert inner.attributes["tenant"] == "acme"
            emit_query()

        restored = context.current()
        assert restored.operation == "outer"
        assert restored.job_id == "outer-job"
        assert restored.attributes == {"tenant": "acme"}

    assert events[0]["operation"] == "orders"
    assert events[0]["job_id"] == "run-inner"


def test_configured_attributes_override_extracted_attributes(events: list[dict]) -> None:
    dagster_context = SimpleNamespace(
        run_id="run-123",
        job_name="asset_job",
        op_name="orders_op",
        asset_key=AssetKey("orders"),
    )

    with datacontext.use_dagster_context(
        dagster_context,
        attributes={
            "dagster.job_name": "override_job",
            "dagster.asset_key": "override_asset",
            "team": "analytics",
        },
    ):
        emit_query()

    assert events[0]["operation"] == "orders"
    assert events[0]["attributes"]["dagster.job_name"] == "override_job"
    assert events[0]["attributes"]["dagster.asset_key"] == "override_asset"
    assert events[0]["attributes"]["team"] == "analytics"


def test_run_tags_are_opt_in(events: list[dict]) -> None:
    dagster_context = SimpleNamespace(
        run_id="run-tags",
        job_name="asset_job",
        op_name="orders_op",
        asset_key=AssetKey("orders"),
        run_tags={"env": "prod", "priority": 1},
    )

    with datacontext.use_dagster_context(dagster_context):
        emit_query()
    with datacontext.use_dagster_context(dagster_context, include_run_tags=True):
        emit_query()

    assert "dagster.run_tags" not in events[0]["attributes"]
    assert events[1]["attributes"]["dagster.run_tags"] == {
        "env": "prod",
        "priority": "1",
    }


def test_public_exports_are_available() -> None:
    assert datacontext.use_dagster_context is not None
    assert datacontext.DataContextResource is not None


def test_resource_optional_dependency_has_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = builtins.__import__

    def import_without_dagster(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "dagster":
            raise ImportError("No module named dagster")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_dagster)
    resource_class = dagster_module._build_datacontext_resource_class()

    with pytest.raises(ImportError, match=r"datacontext\[dagster\]"):
        resource_class()
