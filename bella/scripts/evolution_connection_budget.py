"""Report whether Evolution is within its PostgreSQL connection budget.

The command deliberately connects as the dedicated ``evolution`` role. That
role can inspect all of its own sessions without broadening Bella's database
permissions. The observer connection excludes itself from the count.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import getpass
import json
import os
import sys
import time
from typing import Any, TextIO

from psycopg import connect as connect
from psycopg.conninfo import make_conninfo


WARNING_THRESHOLD = 24
DEFAULT_ROLE_LIMIT = 30
UNAVAILABLE_EXIT = 3
WARNING_EXIT = 2

GROUPED_SESSIONS_QUERY = """
SELECT
    COALESCE(datname, '<none>') AS database,
    COALESCE(state, '<unknown>') AS state,
    COALESCE(NULLIF(application_name, ''), '<unspecified>') AS application,
    COALESCE(client_addr::text, client_hostname, '<local>') AS client,
    COUNT(*)::integer AS sessions
FROM pg_stat_activity
WHERE usename = 'evolution'
  AND pid <> pg_backend_pid()
GROUP BY datname, state, application_name, client_addr, client_hostname
ORDER BY database, state, application, client
"""


@dataclass(frozen=True)
class SessionGroup:
    database: str
    state: str
    application: str
    client: str
    sessions: int


@dataclass(frozen=True)
class Snapshot:
    sample: int
    groups: list[SessionGroup]
    total: int
    delta: int | None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check Evolution's PostgreSQL session budget safely."
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=1,
        help="number of samples to collect (default: 1)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="seconds between samples (default: 5)",
    )
    parser.add_argument(
        "--json", action="store_true", help="emit one machine-readable JSON result"
    )
    parser.add_argument(
        "--prompt-password",
        action="store_true",
        help="securely prompt for the evolution database password",
    )
    parser.add_argument(
        "--host",
        help="PostgreSQL host (default: POSTGRES_HOST or postgres)",
    )
    parser.add_argument(
        "--port",
        help="PostgreSQL port (default: POSTGRES_PORT or 5432)",
    )
    return parser


def _connection_dsn(
    environ: Mapping[str, str],
    *,
    password: str | None = None,
    host: str | None = None,
    port: str | None = None,
) -> str | None:
    explicit = environ.get("EVOLUTION_CONNECTION_BUDGET_DSN") or environ.get(
        "POSTGRES_AUTH_DB"
    )
    if explicit:
        return explicit

    password = password or environ.get("EVOLUTION_DB_PASSWORD")
    if not password:
        return None
    return make_conninfo(
        host=host or environ.get("POSTGRES_HOST", "postgres"),
        port=port or environ.get("POSTGRES_PORT", "5432"),
        dbname=environ.get("POSTGRES_DATABASE", "evogo_auth"),
        user="evolution",
        password=password,
        application_name="bella-evolution-budget-check",
    )


def _role_limit(environ: Mapping[str, str]) -> int:
    raw = environ.get("EVOLUTION_DB_CONNECTION_LIMIT", str(DEFAULT_ROLE_LIMIT))
    limit = int(raw)
    if limit < 1:
        raise ValueError("EVOLUTION_DB_CONNECTION_LIMIT must be a positive integer")
    return limit


def _sample(dsn: str) -> list[SessionGroup]:
    with connect(dsn, connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute(GROUPED_SESSIONS_QUERY)
            rows = cursor.fetchall()
    return [
        SessionGroup(
            database=str(row[0]),
            state=str(row[1]),
            application=str(row[2]),
            client=str(row[3]),
            sessions=int(row[4]),
        )
        for row in rows
    ]


def _is_monotonic_growth(totals: Sequence[int]) -> bool:
    return len(totals) > 1 and all(
        current > previous for previous, current in zip(totals, totals[1:])
    )


def _write_human(
    snapshots: Sequence[Snapshot],
    *,
    limit: int,
    warning: bool,
    monotonic_growth: bool,
    stdout: TextIO,
) -> None:
    print("Evolution PostgreSQL connection budget", file=stdout)
    for snapshot in snapshots:
        for group in snapshot.groups:
            print(
                f"database={group.database} state={group.state} "
                f"application={group.application} client={group.client} "
                f"sessions={group.sessions}",
                file=stdout,
            )
        delta = "n/a" if snapshot.delta is None else f"{snapshot.delta:+d}"
        print(
            f"sample={snapshot.sample} total={snapshot.total} delta={delta}",
            file=stdout,
        )

    status = "WARNING" if warning else "OK"
    trend = "MONOTONIC_GROWTH" if monotonic_growth else "STABLE_OR_MIXED"
    last_total = snapshots[-1].total
    print(
        f"total={last_total} limit={limit} threshold={WARNING_THRESHOLD} "
        f"status={status}",
        file=stdout,
    )
    print(
        f"trend={trend} status={status}",
        file=stdout,
    )


def _write_json(
    snapshots: Sequence[Snapshot],
    *,
    limit: int,
    warning: bool,
    monotonic_growth: bool,
    stdout: TextIO,
) -> None:
    result = {
        "status": "warning" if warning else "ok",
        "total": snapshots[-1].total,
        "limit": limit,
        "threshold": WARNING_THRESHOLD,
        "trend": "monotonic_growth" if monotonic_growth else "stable_or_mixed",
        "samples": [asdict(snapshot) for snapshot in snapshots],
    }
    print(json.dumps(result, sort_keys=True), file=stdout)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    sleep: Callable[[float], Any] = time.sleep,
    password_reader: Callable[[str], str] = getpass.getpass,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the operator check and return 0 (ok), 2 (warning), or 3 (unavailable)."""
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    args = _parser().parse_args(argv)
    if args.samples < 1 or args.interval < 0:
        print("ERROR: --samples must be positive and --interval cannot be negative", file=stderr)
        return UNAVAILABLE_EXIT

    current_environ = os.environ if environ is None else environ
    prompted_password = None
    if args.prompt_password:
        prompted_password = password_reader("Evolution database password: ")
    dsn = _connection_dsn(
        current_environ,
        password=prompted_password,
        host=args.host,
        port=args.port,
    )
    if dsn is None:
        print(
            "ERROR: PostgreSQL unavailable: provide EVOLUTION_CONNECTION_BUDGET_DSN, "
            "POSTGRES_AUTH_DB, or EVOLUTION_DB_PASSWORD.",
            file=stderr,
        )
        return UNAVAILABLE_EXIT
    try:
        limit = _role_limit(current_environ)
    except (TypeError, ValueError):
        print(
            "ERROR: EVOLUTION_DB_CONNECTION_LIMIT must be a positive integer.",
            file=stderr,
        )
        return UNAVAILABLE_EXIT

    snapshots: list[Snapshot] = []
    try:
        for sample_number in range(1, args.samples + 1):
            if sample_number > 1:
                sleep(args.interval)
            groups = _sample(dsn)
            total = sum(group.sessions for group in groups)
            previous = snapshots[-1].total if snapshots else None
            snapshots.append(
                Snapshot(
                    sample=sample_number,
                    groups=groups,
                    total=total,
                    delta=None if previous is None else total - previous,
                )
            )
    except Exception:
        # Database exceptions can include the connection string. Keep the
        # operator result actionable without echoing credentials or a traceback.
        print(
            "ERROR: PostgreSQL unavailable; the Evolution connection budget "
            "could not be sampled. Treat a role-limit refusal as an incident.",
            file=stderr,
        )
        return UNAVAILABLE_EXIT

    totals = [snapshot.total for snapshot in snapshots]
    monotonic_growth = _is_monotonic_growth(totals)
    warning = any(total >= WARNING_THRESHOLD for total in totals) or monotonic_growth
    if args.json:
        _write_json(
            snapshots,
            limit=limit,
            warning=warning,
            monotonic_growth=monotonic_growth,
            stdout=stdout,
        )
    else:
        _write_human(
            snapshots,
            limit=limit,
            warning=warning,
            monotonic_growth=monotonic_growth,
            stdout=stdout,
        )
    return WARNING_EXIT if warning else 0


if __name__ == "__main__":
    raise SystemExit(main())
