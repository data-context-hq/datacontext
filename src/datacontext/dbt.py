from __future__ import annotations

from typing import Any, ContextManager, Mapping

from datacontext import context as datacontext_context


def use_dbt_context(
    dbt_context: Any,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> ContextManager[datacontext_context.TraceContext]:
    extracted = _extract_dbt_context(dbt_context)
    merged_attributes = dict(extracted["attributes"])
    if attributes:
        merged_attributes.update(attributes)
    return datacontext_context.use(
        operation=extracted["operation"],
        job_id=extracted["job_id"],
        attributes=merged_attributes,
    )


def _extract_dbt_context(dbt_context: Any) -> dict[str, Any]:
    node = _extract_node(dbt_context)
    target = _safe_get(dbt_context, "target")
    this_relation = _safe_get(dbt_context, "this")
    invocation_id = _safe_str(
        _first_present(
            _safe_get(dbt_context, "invocation_id"),
            _safe_get(_safe_get(dbt_context, "metadata"), "invocation_id"),
        )
    )
    unique_id = _safe_str(_safe_get(node, "unique_id"))
    node_name = _safe_str(_safe_get(node, "name"))
    resource_type = _safe_str(_safe_get(node, "resource_type"))
    package_name = _safe_str(_safe_get(node, "package_name"))
    original_file_path = _safe_str(_safe_get(node, "original_file_path"))
    path = _safe_str(_safe_get(node, "path"))
    relation_name = _safe_str(_safe_get(node, "relation_name"))
    this_name = _safe_str(this_relation)

    attributes: dict[str, Any] = {}
    _put(attributes, "dbt.invocation_id", invocation_id)
    _put(attributes, "dbt.node.unique_id", unique_id)
    _put(attributes, "dbt.node.name", node_name)
    _put(attributes, "dbt.node.resource_type", resource_type)
    _put(attributes, "dbt.node.package_name", package_name)
    _put(attributes, "dbt.node.original_file_path", original_file_path)
    _put(attributes, "dbt.node.path", path)
    _put(attributes, "dbt.node.relation_name", relation_name)
    _put(attributes, "dbt.this", this_name)
    _put_relation_attributes(attributes, this_relation, "dbt.this")
    _put_target_attributes(attributes, target)

    tags = _normalize_sequence(_safe_get(node, "tags"))
    if tags:
        attributes["dbt.node.tags"] = tags

    return {
        "job_id": invocation_id,
        "operation": unique_id or relation_name or this_name or node_name,
        "attributes": attributes,
    }


def _extract_node(dbt_context: Any) -> Any:
    for name in ("model", "node"):
        value = _safe_get(dbt_context, name)
        if value is not None:
            return value
    if _safe_get(dbt_context, "unique_id") is not None:
        return dbt_context
    return None


def _put_target_attributes(attributes: dict[str, Any], target: Any) -> None:
    for name in ("name", "type", "database", "schema", "warehouse"):
        _put(attributes, f"dbt.target.{name}", _safe_str(_safe_get(target, name)))


def _put_relation_attributes(
    attributes: dict[str, Any],
    relation: Any,
    prefix: str,
) -> None:
    for name in ("database", "schema", "identifier"):
        _put(attributes, f"{prefix}.{name}", _safe_str(_safe_get(relation, name)))


def _safe_get(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(name)
    try:
        return getattr(value, name)
    except Exception:
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _normalize_sequence(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value]


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value


__all__ = ["use_dbt_context"]
