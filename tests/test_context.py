from __future__ import annotations

from datacontext import context


def test_context_use_sets_and_restores_values() -> None:
    with context.use(operation="checkout", actor="user:1", attributes={"tenant": "acme"}):
        current = context.current()
        assert current.operation == "checkout"
        assert current.actor == "user:1"
        assert current.attributes == {"tenant": "acme"}

    current = context.current()
    assert current.operation is None
    assert current.attributes == {}


def test_nested_context_merges_attributes() -> None:
    with context.use(operation="outer", attributes={"tenant": "acme"}):
        with context.use(request_id="req", attributes={"region": "us"}):
            current = context.current()
            assert current.operation == "outer"
            assert current.request_id == "req"
            assert current.attributes == {"tenant": "acme", "region": "us"}

