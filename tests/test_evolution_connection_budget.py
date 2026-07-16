"""Behavior tests for the Evolution PostgreSQL connection-budget command."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

import pytest

from bella.scripts import evolution_connection_budget
from bella.scripts.evolution_connection_policy import (
    ROLE_CONNECTION_LIMIT,
    WARNING_THRESHOLD,
)


Row = tuple[str, str, str, str, int]


class FakeCursor:
    def __init__(self, rows: Sequence[Row], role_limit: int) -> None:
        self._rows = rows
        self._role_limit = role_limit

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: object, params: object = None) -> None:
        return None

    def fetchall(self) -> Sequence[Row]:
        return self._rows

    def fetchone(self) -> tuple[int, str]:
        return self._role_limit, "evolution"


class FakeConnection:
    def __init__(self, rows: Sequence[Row], role_limit: int) -> None:
        self._rows = rows
        self._role_limit = role_limit

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows, self._role_limit)


def sequence_connector(
    samples: Sequence[Sequence[Row]], *, role_limit: int = ROLE_CONNECTION_LIMIT
) -> Any:
    remaining = iter(samples)

    @contextmanager
    def connect(dsn: str, *, connect_timeout: int) -> Iterator[FakeConnection]:
        yield FakeConnection(next(remaining), role_limit)

    return connect


def run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    samples: Sequence[Sequence[Row]],
    *,
    argv: Sequence[str] = (),
    environ: Mapping[str, str] | None = None,
    role_limit: int = ROLE_CONNECTION_LIMIT,
) -> tuple[int, str, str]:
    monkeypatch.setattr(
        evolution_connection_budget,
        "connect",
        sequence_connector(samples, role_limit=role_limit),
    )
    code = evolution_connection_budget.main(
        list(argv),
        environ=environ
        if environ is not None
        else {
            "EVOLUTION_CONNECTION_BUDGET_DSN": "postgresql://evolution:secret@postgres/evogo_auth",
            "EVOLUTION_DB_CONNECTION_LIMIT": str(ROLE_CONNECTION_LIMIT),
        },
        sleep=lambda seconds: None,
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def grouped_rows(total: int) -> list[Row]:
    return [("evogo_auth", "idle", "evolution-go", "172.20.0.4", total)]


def test_low_count_is_within_budget_and_reports_group_identity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, stdout, stderr = run(monkeypatch, capsys, [grouped_rows(7)])

    assert code == 0
    assert "evogo_auth" in stdout
    assert "idle" in stdout
    assert "evolution-go" in stdout
    assert "172.20.0.4" in stdout
    assert (
        f"total=7 limit={ROLE_CONNECTION_LIMIT} threshold={WARNING_THRESHOLD} status=OK"
        in stdout
    )
    assert f"configured_limit={ROLE_CONNECTION_LIMIT}" in stdout
    assert stderr == ""


@pytest.mark.parametrize("total", [24, 29])
def test_count_at_or_above_threshold_returns_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    total: int,
) -> None:
    code, stdout, _ = run(monkeypatch, capsys, [grouped_rows(total)])

    assert code == 2
    assert f"total={total} limit=30 threshold=24 status=WARNING" in stdout


def test_unavailable_postgres_fails_cleanly_without_exposing_the_dsn(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    secret_dsn = "postgresql://evolution:never-print-me@postgres/evogo_auth"

    def unavailable(dsn: str, *, connect_timeout: int) -> Any:
        raise OSError(f"could not connect using {dsn}")

    monkeypatch.setattr(evolution_connection_budget, "connect", unavailable)
    code = evolution_connection_budget.main(
        [],
        environ={"EVOLUTION_CONNECTION_BUDGET_DSN": secret_dsn},
        sleep=lambda seconds: None,
    )
    captured = capsys.readouterr()

    assert code == 3
    assert "PostgreSQL unavailable" in captured.err
    assert "never-print-me" not in captured.out + captured.err
    assert "Traceback" not in captured.err


def test_repeated_samples_make_monotonic_growth_a_warning_below_threshold(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, stdout, _ = run(
        monkeypatch,
        capsys,
        [grouped_rows(8), grouped_rows(11), grouped_rows(14)],
        argv=["--samples", "3", "--interval", "0"],
    )

    assert code == 2
    assert "sample=1 total=8 delta=n/a" in stdout
    assert "sample=2 total=11 delta=+3" in stdout
    assert "sample=3 total=14 delta=+3" in stdout
    assert "trend=MONOTONIC_GROWTH status=WARNING" in stdout


def test_json_mode_exposes_a_machine_readable_status(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, stdout, _ = run(
        monkeypatch, capsys, [grouped_rows(24)], argv=["--json"]
    )

    assert code == 2
    assert '"status": "warning"' in stdout
    assert '"threshold": 24' in stdout
    assert '"configured_limit": 30' in stdout


def test_role_limit_is_observed_from_postgres_when_environment_is_absent(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, stdout, stderr = run(
        monkeypatch,
        capsys,
        [grouped_rows(7)],
        environ={
            "EVOLUTION_CONNECTION_BUDGET_DSN": (
                "postgresql://evolution:secret@postgres/evogo_auth"
            )
        },
    )

    assert code == 0
    assert "limit=30" in stdout
    assert "configured_limit=30" in stdout
    assert stderr == ""


def test_role_limit_drift_fails_safely_and_reports_both_values(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, stdout, stderr = run(
        monkeypatch,
        capsys,
        [grouped_rows(7)],
        role_limit=29,
    )

    assert code == 3
    assert stdout == ""
    assert "actual role limit 29" in stderr
    assert "configured expected limit 30" in stderr


def test_operator_can_enter_the_database_password_without_echoing_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        evolution_connection_budget,
        "connect",
        sequence_connector([grouped_rows(3)]),
    )
    code = evolution_connection_budget.main(
        ["--prompt-password", "--host", "127.0.0.1"],
        environ={},
        password_reader=lambda prompt: "never-print-me",
        sleep=lambda seconds: None,
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "never-print-me" not in captured.out + captured.err
