from __future__ import annotations

from contextlib import ExitStack, contextmanager
from typing import Any, ContextManager, Iterator, Mapping

from datacontext import context as datacontext_context
from datacontext.config import configured, get_config


def use_dagster_context(
    dagster_context: Any,
    *,
    attributes: Mapping[str, Any] | None = None,
    include_run_tags: bool = False,
) -> ContextManager[datacontext_context.TraceContext]:
    extracted = _extract_dagster_context(
        dagster_context,
        include_run_tags=include_run_tags,
    )
    merged_attributes = dict(extracted["attributes"])
    if attributes:
        merged_attributes.update(attributes)
    return datacontext_context.use(
        operation=extracted["operation"],
        job_id=extracted["job_id"],
        attributes=merged_attributes,
    )


def _build_datacontext_resource_class() -> type[Any]:
    try:
        from dagster import ConfigurableResource
    except ImportError:

        class MissingDataContextResource:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                raise ImportError(
                    "Dagster support requires the optional dependency. "
                    'Install it with: pip install "datacontext[dagster]"'
                )

        return MissingDataContextResource

    class DataContextResource(ConfigurableResource):  # type: ignore[misc, valid-type]
        service_name: str | None = None
        environment: str | None = None
        include_run_tags: bool = False

        @contextmanager
        def use_context(
            self,
            dagster_context: Any,
            *,
            attributes: Mapping[str, Any] | None = None,
        ) -> Iterator[datacontext_context.TraceContext]:
            current_config = get_config()
            with ExitStack() as stack:
                if self.service_name is not None or self.environment is not None:
                    stack.enter_context(
                        configured(
                            service_name=self.service_name
                            if self.service_name is not None
                            else current_config.service_name,
                            environment=self.environment
                            if self.environment is not None
                            else current_config.environment,
                            sink=current_config.sink,
                            include_query_text=current_config.include_query_text,
                            include_raw_query_text=current_config.include_raw_query_text,
                        )
                    )
                trace_context = stack.enter_context(
                    use_dagster_context(
                        dagster_context,
                        attributes=attributes,
                        include_run_tags=self.include_run_tags,
                    )
                )
                yield trace_context

    return DataContextResource


DataContextResource = _build_datacontext_resource_class()


def _extract_dagster_context(
    dagster_context: Any,
    *,
    include_run_tags: bool,
) -> dict[str, Any]:
    run_id = _safe_str(_safe_getattr(dagster_context, "run_id"))
    job_name = _safe_str(_safe_getattr(dagster_context, "job_name"))
    op_name = _extract_op_name(dagster_context)
    asset_key = _extract_asset_key(dagster_context)
    partition_key = _safe_str(_safe_getattr(dagster_context, "partition_key"))

    attributes: dict[str, Any] = {}
    _put(attributes, "dagster.run_id", run_id)
    _put(attributes, "dagster.job_name", job_name)
    _put(attributes, "dagster.op_name", op_name)
    _put(attributes, "dagster.asset_key", asset_key)
    _put(attributes, "dagster.partition_key", partition_key)

    if include_run_tags:
        run_tags = _extract_run_tags(dagster_context)
        if run_tags:
            attributes["dagster.run_tags"] = run_tags

    return {
        "job_id": run_id,
        "operation": asset_key or op_name,
        "attributes": attributes,
    }


def _extract_op_name(dagster_context: Any) -> str | None:
    op_name = _safe_str(_safe_getattr(dagster_context, "op_name"))
    if op_name:
        return op_name
    op = _safe_getattr(dagster_context, "op")
    name = _safe_str(_safe_getattr(op, "name")) if op is not None else None
    if name:
        return name
    solid_handle = _safe_getattr(dagster_context, "solid_handle")
    return _safe_str(_safe_getattr(solid_handle, "name")) if solid_handle else None


def _extract_asset_key(dagster_context: Any) -> str | None:
    asset_key = _safe_getattr(dagster_context, "asset_key")
    if asset_key is None:
        return None
    to_user_string = _safe_getattr(asset_key, "to_user_string")
    if callable(to_user_string):
        try:
            value = to_user_string()
        except Exception:
            value = None
        text = _safe_str(value)
        if text:
            return text
    path = _safe_getattr(asset_key, "path")
    if isinstance(path, (list, tuple)) and path:
        return "/".join(str(part) for part in path)
    return _safe_str(asset_key)


def _extract_run_tags(dagster_context: Any) -> dict[str, str]:
    tags = _safe_getattr(dagster_context, "run_tags")
    if not tags:
        dagster_run = _safe_getattr(dagster_context, "dagster_run")
        tags = _safe_getattr(dagster_run, "tags") if dagster_run is not None else None
    if not isinstance(tags, Mapping):
        return {}
    return {str(key): str(value) for key, value in tags.items()}


def _safe_getattr(value: Any, name: str) -> Any:
    try:
        return getattr(value, name)
    except Exception:
        return None


def _safe_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _put(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None:
        target[key] = value


__all__ = ["DataContextResource", "use_dagster_context"]
