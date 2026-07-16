"""Prove the Evolution role limit preserves Bella and administrator capacity.

Run only against a disposable stack with Evolution stopped and no existing
Evolution sessions. All deliberately opened sessions are closed in ``finally``.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
import getpass
import json
import os
import sys
from typing import Any, TextIO

from psycopg import connect as connect
from psycopg.conninfo import make_conninfo

from bella.scripts.evolution_connection_policy import (
    EVOLUTION_ROLE,
    ROLE_CONNECTION_LIMIT,
)

TOO_MANY_CONNECTIONS_SQLSTATE = "53300"
FAILURE_EXIT = 3


class ProofFailure(RuntimeError):
    """The disposable capacity proof did not establish the required behavior."""


@dataclass(frozen=True)
class ProofResult:
    opened_evolution_sessions: int
    rejected_sqlstate: str
    bella_query_succeeded: bool
    admin_query_succeeded: bool
    cleaned_up: bool


def _scalar(connection: Any, query: str, params: object = None) -> int:
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        row = cursor.fetchone()
    if row is None:
        raise ProofFailure("PostgreSQL did not return the required proof value")
    return int(row[0])


def prove_capacity(
    *,
    evolution_dsn: str,
    bella_dsn: str,
    admin_dsn: str,
    connector: Callable[..., Any] = connect,
) -> ProofResult:
    """Open 30 Evolution sessions, require the 31st refusal, and clean up."""
    connections: list[Any] = []
    rejected_sqlstate = ""
    bella_ok = False
    admin_ok = False
    cleaned_up = True
    try:
        first_evolution = connector(evolution_dsn, connect_timeout=5)
        connections.append(first_evolution)
        role_limit = _scalar(
            first_evolution,
            "SELECT rolconnlimit FROM pg_roles WHERE rolname = %s",
            (EVOLUTION_ROLE,),
        )
        if role_limit != ROLE_CONNECTION_LIMIT:
            raise ProofFailure(
                f"Evolution role limit is {role_limit}, expected {ROLE_CONNECTION_LIMIT}"
            )
        existing = _scalar(
            first_evolution,
            "SELECT count(*) FROM pg_stat_activity "
            "WHERE usename = %s AND pid <> pg_backend_pid()",
            (EVOLUTION_ROLE,),
        )
        if existing != 0:
            raise ProofFailure(
                f"Evolution must be stopped with zero existing sessions; found {existing}"
            )

        if _scalar(first_evolution, "SELECT 1") != 1:
            raise ProofFailure("an Evolution proof session could not query PostgreSQL")
        for _ in range(ROLE_CONNECTION_LIMIT - 1):
            evolution = connector(evolution_dsn, connect_timeout=5)
            connections.append(evolution)
            if _scalar(evolution, "SELECT 1") != 1:
                raise ProofFailure("an Evolution proof session could not query PostgreSQL")

        try:
            unexpected = connector(evolution_dsn, connect_timeout=5)
        except Exception as exc:
            rejected_sqlstate = str(getattr(exc, "sqlstate", ""))
            if rejected_sqlstate != TOO_MANY_CONNECTIONS_SQLSTATE:
                raise ProofFailure(
                    "the 31st Evolution connection did not fail with SQLSTATE 53300"
                ) from exc
        else:
            connections.append(unexpected)
            raise ProofFailure("the 31st Evolution connection was unexpectedly accepted")

        # These must be new connections, established only after Evolution is
        # demonstrably saturated, otherwise they do not prove reserved access.
        bella = connector(bella_dsn, connect_timeout=5)
        connections.append(bella)
        admin = connector(admin_dsn, connect_timeout=5)
        connections.append(admin)
        bella_ok = _scalar(bella, "SELECT 1") == 1
        admin_ok = _scalar(admin, "SELECT 1") == 1
        if not bella_ok or not admin_ok:
            raise ProofFailure(
                "Bella and administrator queries must succeed at Evolution saturation"
            )
    finally:
        for connection in reversed(connections):
            try:
                connection.close()
            except Exception:
                # Continue cleanup so one broken connection cannot strand the rest,
                # but never report a passing proof if cleanup was incomplete.
                cleaned_up = False
    if not cleaned_up:
        raise ProofFailure("one or more proof sessions could not be closed")
    return ProofResult(
        opened_evolution_sessions=ROLE_CONNECTION_LIMIT,
        rejected_sqlstate=rejected_sqlstate,
        bella_query_succeeded=bella_ok,
        admin_query_succeeded=admin_ok,
        cleaned_up=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Disposable proof that Evolution's 30-session role limit preserves "
            "Bella and PostgreSQL administrator access."
        )
    )
    parser.add_argument("--host", help="PostgreSQL host (default: postgres)")
    parser.add_argument("--port", help="PostgreSQL port (default: 5432)")
    parser.add_argument(
        "--prompt-passwords",
        action="store_true",
        help="securely prompt for Evolution, Bella, and administrator passwords",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def _role_dsn(
    environ: Mapping[str, str],
    *,
    role: str,
    database: str,
    password: str | None,
    host: str | None,
    port: str | None,
) -> str | None:
    explicit_names = {
        EVOLUTION_ROLE: ("EVOLUTION_CONNECTION_BUDGET_DSN", "POSTGRES_AUTH_DB"),
        "bella": ("BELLA_DATABASE_URL",),
        "admin": ("POSTGRES_ADMIN_DSN",),
    }
    if password is None:
        for name in explicit_names[role]:
            if dsn := environ.get(name):
                return dsn
    password_names = {
        EVOLUTION_ROLE: "EVOLUTION_DB_PASSWORD",
        "bella": "BELLA_DB_PASSWORD",
        "admin": "POSTGRES_PASSWORD",
    }
    password = password or environ.get(password_names[role])
    if not password:
        return None
    user = environ.get("POSTGRES_USER", "postgres") if role == "admin" else role
    return make_conninfo(
        host=host or environ.get("POSTGRES_HOST", "postgres"),
        port=port or environ.get("POSTGRES_PORT", "5432"),
        dbname=database,
        user=user,
        password=password,
        application_name="bella-evolution-role-limit-proof",
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    password_reader: Callable[[str], str] = getpass.getpass,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = sys.stdout if stdout is None else stdout
    stderr = sys.stderr if stderr is None else stderr
    args = _parser().parse_args(argv)
    current_environ = os.environ if environ is None else environ
    passwords: dict[str, str | None] = {
        EVOLUTION_ROLE: None,
        "bella": None,
        "admin": None,
    }
    if args.prompt_passwords:
        passwords = {
            EVOLUTION_ROLE: password_reader("Evolution database password: "),
            "bella": password_reader("Bella database password: "),
            "admin": password_reader("PostgreSQL administrator password: "),
        }
    dsns = {
        EVOLUTION_ROLE: _role_dsn(
            current_environ,
            role=EVOLUTION_ROLE,
            database=current_environ.get("POSTGRES_DATABASE", "evogo_auth"),
            password=passwords[EVOLUTION_ROLE],
            host=args.host,
            port=args.port,
        ),
        "bella": _role_dsn(
            current_environ,
            role="bella",
            database="bella",
            password=passwords["bella"],
            host=args.host,
            port=args.port,
        ),
        "admin": _role_dsn(
            current_environ,
            role="admin",
            database="postgres",
            password=passwords["admin"],
            host=args.host,
            port=args.port,
        ),
    }
    if any(dsn is None for dsn in dsns.values()):
        print(
            "ERROR: provide all three database credentials through the documented "
            "environment variables or --prompt-passwords.",
            file=stderr,
        )
        return FAILURE_EXIT
    try:
        result = prove_capacity(
            evolution_dsn=str(dsns[EVOLUTION_ROLE]),
            bella_dsn=str(dsns["bella"]),
            admin_dsn=str(dsns["admin"]),
        )
    except Exception:
        print(
            "ERROR: disposable role-limit proof failed; all opened proof sessions "
            "were closed. Check prerequisites and PostgreSQL logs.",
            file=stderr,
        )
        return FAILURE_EXIT
    if args.json:
        print(json.dumps(asdict(result), sort_keys=True), file=stdout)
    else:
        print(
            "PASS: opened 30 Evolution sessions; the 31st was rejected with "
            "SQLSTATE 53300; Bella and administrator queries succeeded; all proof "
            "sessions were closed.",
            file=stdout,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
