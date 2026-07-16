"""Behavior tests for the disposable Evolution role-capacity proof."""

from __future__ import annotations

from typing import Any

import pytest

from bella.scripts.evolution_connection_limit_proof import ProofFailure, prove_capacity


class FakeRoleLimitError(Exception):
    sqlstate = "53300"


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.query = ""

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: object, params: object = None) -> None:
        self.query = str(query)

    def fetchone(self) -> tuple[int]:
        if "rolconnlimit" in self.query:
            return (30,)
        if "pg_stat_activity" in self.query:
            return (0,)
        return (1,)


class FakeConnection:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.closed = False

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed = True


class FakeConnector:
    def __init__(self) -> None:
        self.evolution_count = 0
        self.connections: list[FakeConnection] = []
        self.calls: list[str] = []

    def __call__(self, dsn: str, *, connect_timeout: int) -> FakeConnection:
        self.calls.append(dsn)
        if dsn == "evolution":
            self.evolution_count += 1
            if self.evolution_count == 31:
                raise FakeRoleLimitError("too many connections for role")
        connection = FakeConnection(dsn)
        self.connections.append(connection)
        return connection


def test_proof_opens_limit_rejects_next_and_cleans_up() -> None:
    connector = FakeConnector()

    result = prove_capacity(
        evolution_dsn="evolution",
        bella_dsn="bella",
        admin_dsn="admin",
        connector=connector,
    )

    assert result.opened_evolution_sessions == 30
    assert result.rejected_sqlstate == "53300"
    assert result.bella_query_succeeded is True
    assert result.admin_query_succeeded is True
    assert connector.calls[:31] == ["evolution"] * 31
    assert connector.calls[31:] == ["bella", "admin"]
    assert all(connection.closed for connection in connector.connections)


def test_proof_does_not_mistake_an_unrelated_failure_for_role_rejection() -> None:
    connector = FakeConnector()

    def fail_with_network_error(dsn: str, *, connect_timeout: int) -> Any:
        if dsn == "evolution" and connector.evolution_count == 30:
            raise OSError("network unavailable")
        return connector(dsn, connect_timeout=connect_timeout)

    with pytest.raises(ProofFailure, match="SQLSTATE 53300"):
        prove_capacity(
            evolution_dsn="evolution",
            bella_dsn="bella",
            admin_dsn="admin",
            connector=fail_with_network_error,
        )

    assert all(connection.closed for connection in connector.connections)
