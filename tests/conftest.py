from __future__ import annotations

import pytest

import datacontext
from datacontext import context


@pytest.fixture(autouse=True)
def reset_datacontext() -> None:
    datacontext.reset_config()
    context.reset()


@pytest.fixture
def events() -> list[dict]:
    captured: list[dict] = []
    datacontext.configure(
        service_name="svc",
        environment="test",
        sink=type("Sink", (), {"emit": lambda self, event: captured.append(dict(event))})(),
    )
    return captured

