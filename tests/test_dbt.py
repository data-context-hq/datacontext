from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import datacontext
from datacontext import context


class Relation:
    database = "analytics"
    schema = "mart"
    identifier = "orders"

    def __str__(self) -> str:
        return "analytics.mart.orders"


class RaisingRelationContext:
    invocation_id = "run-456"
    model = SimpleNamespace(unique_id="model.shop.customers", name="customers")

    @property
    def this(self) -> Any:
        raise RuntimeError("relation not available")


def emit_query() -> dict[str, Any]:
    return datacontext.capture_query(
        db_system="snowflake",
        client="dbt",
        query="select * from orders where id = 1",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T00:00:01Z",
        duration_ms=1000,
        status="ok",
    )


def test_python_model_context_metadata_extraction(events: list[dict]) -> None:
    dbt_context = SimpleNamespace(
        invocation_id="run-123",
        this=Relation(),
        target={
            "name": "prod",
            "type": "snowflake",
            "database": "analytics",
            "schema": "mart",
            "warehouse": "transforming",
        },
        model=SimpleNamespace(
            unique_id="model.shop.orders",
            name="orders",
            resource_type="model",
            package_name="shop",
            original_file_path="models/orders.py",
            path="orders.py",
            tags=["daily", "finance"],
        ),
    )

    with datacontext.use_dbt_context(dbt_context):
        emit_query()

    event = events[0]
    assert event["job_id"] == "run-123"
    assert event["operation"] == "model.shop.orders"
    assert event["attributes"] == {
        "dbt.invocation_id": "run-123",
        "dbt.node.unique_id": "model.shop.orders",
        "dbt.node.name": "orders",
        "dbt.node.resource_type": "model",
        "dbt.node.package_name": "shop",
        "dbt.node.original_file_path": "models/orders.py",
        "dbt.node.path": "orders.py",
        "dbt.this": "analytics.mart.orders",
        "dbt.this.database": "analytics",
        "dbt.this.schema": "mart",
        "dbt.this.identifier": "orders",
        "dbt.target.name": "prod",
        "dbt.target.type": "snowflake",
        "dbt.target.database": "analytics",
        "dbt.target.schema": "mart",
        "dbt.target.warehouse": "transforming",
        "dbt.node.tags": ["daily", "finance"],
    }


def test_artifact_mapping_metadata_extraction(events: list[dict]) -> None:
    dbt_context = {
        "metadata": {"invocation_id": "artifact-run"},
        "node": {
            "unique_id": "model.shop.payments",
            "name": "payments",
            "resource_type": "model",
            "package_name": "shop",
            "relation_name": '"analytics"."mart"."payments"',
        },
    }

    with datacontext.use_dbt_context(dbt_context):
        emit_query()

    event = events[0]
    assert event["job_id"] == "artifact-run"
    assert event["operation"] == "model.shop.payments"
    assert event["attributes"]["dbt.node.relation_name"] == '"analytics"."mart"."payments"'


def test_nested_datacontext_context_restoration(events: list[dict]) -> None:
    dbt_context = SimpleNamespace(
        invocation_id="run-inner",
        this=Relation(),
        model=SimpleNamespace(unique_id="model.shop.orders", name="orders"),
    )

    with context.use(operation="outer", job_id="outer-job", attributes={"tenant": "acme"}):
        with datacontext.use_dbt_context(dbt_context):
            inner = context.current()
            assert inner.operation == "model.shop.orders"
            assert inner.job_id == "run-inner"
            assert inner.attributes["tenant"] == "acme"
            emit_query()

        restored = context.current()
        assert restored.operation == "outer"
        assert restored.job_id == "outer-job"
        assert restored.attributes == {"tenant": "acme"}

    assert events[0]["operation"] == "model.shop.orders"
    assert events[0]["job_id"] == "run-inner"


def test_configured_attributes_override_extracted_attributes(events: list[dict]) -> None:
    dbt_context = SimpleNamespace(
        invocation_id="run-123",
        this=Relation(),
        model=SimpleNamespace(unique_id="model.shop.orders", name="orders"),
    )

    with datacontext.use_dbt_context(
        dbt_context,
        attributes={
            "dbt.node.unique_id": "override_model",
            "team": "analytics",
        },
    ):
        emit_query()

    assert events[0]["operation"] == "model.shop.orders"
    assert events[0]["attributes"]["dbt.node.unique_id"] == "override_model"
    assert events[0]["attributes"]["team"] == "analytics"


def test_missing_relation_does_not_break_context(events: list[dict]) -> None:
    with datacontext.use_dbt_context(RaisingRelationContext()):
        emit_query()

    assert events[0]["job_id"] == "run-456"
    assert events[0]["operation"] == "model.shop.customers"
    assert "dbt.this" not in events[0]["attributes"]


def test_public_export_is_available() -> None:
    assert datacontext.use_dbt_context is not None
