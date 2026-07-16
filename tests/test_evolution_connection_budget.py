"""Behavior tests for the Evolution PostgreSQL connection-budget command."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any

import pytest

from bella.scripts import evolution_connection_budget


Row = tuple[str, str, str, str, int]


class FakeCursor:
    def __init__(self, rows: Sequence[Row]) -> None:
        self._rows = rows

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: object, params: object = None) -> None:
        return None

    def fetchall(self) -> Sequence[Row]:
        return self._rows


class FakeConnection:
    def __init__(self, rows: Sequence[Row]) -> None:
        self._rows = rows

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._rows)


def sequence_connector(samples: Sequence[Sequence[Row]]) -> Any:
    remaining = iter(samples)

    @contextmanager
    def connect(dsn: str, *, connect_timeout: int) -> Iterator[FakeConnection]:
        yield FakeConnection(next(remaining))

    return connect


def run(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    samples: Sequence[Sequence[Row]],
    *,
    argv: Sequence[str] = (),
    environ: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    monkeypatch.setattr(evolution_connection_budget, "connect", sequence_connector(samples))
    code = evolution_connection_budget.main(
        list(argv),
        environ=environ
        or {
            "EVOLUTION_CONNECTION_BUDGET_DSN": "postgresql://evolution:secret@postgres/evogo_auth",
            "EVOLUTION_DB_CONNECTION_LIMIT": "30",
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
    assert "total=7 limit=30 threshold=24 status=OK" in stdout
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
