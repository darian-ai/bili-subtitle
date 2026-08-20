from __future__ import annotations

import socket
from collections.abc import Iterator
from typing import NoReturn

import pytest


@pytest.fixture(autouse=True)
def deny_unmocked_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Make every real socket connection a deterministic test failure."""

    def blocked(*_args: object, **_kwargs: object) -> NoReturn:
        raise AssertionError("default tests must not access the network")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    yield
