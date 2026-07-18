"""Contract tests for the Compose artifact shared by local Docker and Coolify."""

import hashlib
from pathlib import Path
from typing import Any, cast

import yaml

from bella.scripts.evolution_connection_policy import (
    ROLE_CONNECTION_LIMIT,
    ROLE_IDLE_SESSION_TIMEOUT,
)

ROOT = Path(__file__).resolve().parent.parent
EVOLUTION_IMAGE = (
    "bella/evolution-go:0.7.2-pr117-0328955"
)


def _load_compose(name: str) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        yaml.safe_load((ROOT / name).read_text(encoding="utf-8")),
    )


def test_production_compose_owns_the_three_service_stack_without_host_ports() -> None:
    compose = _load_compose("docker-compose.yml")
    services = compose["services"]

    assert set(services) == {"bella", "evolution-go", "postgres"}
    assert services["evolution-go"]["image"] == EVOLUTION_IMAGE
    assert services["postgres"]["image"] == (
        "postgres:15-alpine@"
        "sha256:3d0f7584ed7d04e27fa050d6683a74746608faf21f202be78460d679cc56461f"
    )
    assert all("ports" not in service for service in services.values())
    assert "/ready" in services["bella"]["healthcheck"]["test"][-1]
    assert "networks" not in compose
    assert set(compose["volumes"]) == {"postgres_data"}
    assert compose["configs"]["postgres_init"]["file"] == (
        "./deploy/postgres/init-databases.sh"
    )


def test_application_database_roles_are_isolated_by_compose_contract() -> None:
    services = _load_compose("docker-compose.yml")["services"]
    bella_environment = services["bella"]["environment"]
    evolution_environment = services["evolution-go"]["environment"]

    assert bella_environment["BELLA_DATABASE_URL"].startswith(
        "postgresql://bella:${BELLA_DB_PASSWORD"
    )
    assert evolution_environment["POSTGRES_AUTH_DB"].startswith(
        "postgresql://evolution:${EVOLUTION_DB_PASSWORD"
    )
    assert evolution_environment["POSTGRES_USERS_DB"].startswith(
        "postgresql://evolution:${EVOLUTION_DB_PASSWORD"
    )
    assert evolution_environment["GIN_MODE"] == "release"
    assert bella_environment["EVOLUTION_URL"] == "http://evolution-go:8080"
    assert bella_environment["BELLA_INTERNAL_URL"] == "http://bella:8000"


def test_evolution_runtime_is_built_from_the_reviewed_pinned_backport() -> None:
    service = _load_compose("docker-compose.yml")["services"]["evolution-go"]
    dockerfile = (ROOT / "deploy/evolution/Dockerfile").read_text(encoding="utf-8")

    assert service["image"] == EVOLUTION_IMAGE
    assert service["build"] == {
        "context": ".",
        "dockerfile": "deploy/evolution/Dockerfile",
    }
    assert "latest" not in service["image"]
    assert "develop" not in dockerfile
    assert "# syntax=" not in dockerfile
    assert (
        "golang:1.25.0-alpine@sha256:"
        "f18a072054848d87a8077455f0ac8a25886f2397f88bfdd222d6fafbb5bba440"
        in dockerfile
    )
    assert (
        "alpine:3.19.1@sha256:"
        "c5b1261d6d3e43071626931fc004f70149baeba2c8ec672bd4f27761f8e1ad6b"
        in dockerfile
    )
    assert "9337afc47e10b86cc896a6f432240e40fee95dd1" in dockerfile
    assert "19bda71777291320199fba91deb8620921fc60e2da1ca602bab533f12014b034" in dockerfile

    patch_hashes = {
        "4cc635dd460f70c36ba83285ecbb34589790572f": (
            "d4c55fde878f585fe4a8cc8ca8081fcd226245ea1c7f281069945c4cee4eb590"
        ),
        "f85ea1445373ea142bb12ba0c01dfc85879be212": (
            "26e40ac1485a606c8647b7fbb61e5c918a8f70009aa344d364dce06123b2d232"
        ),
        "03289559d547911d92ad58837db98faeb0c5fd8e": (
            "f6c4fdc65dd00e4ddc98fccff0246460c266ff8b2f3eb56987a6c844c22465c6"
        ),
    }
    commits = tuple(patch_hashes)
    positions = [dockerfile.index(commit) for commit in commits]
    assert positions == sorted(positions)
    for commit, expected_hash in patch_hashes.items():
        patch = ROOT / f"deploy/evolution/patches/{commit}.patch"
        assert hashlib.sha256(patch.read_bytes()).hexdigest() == expected_hash

    assert "go test ./pkg/whatsmeow/service" in dockerfile
    assert "git=2.49.1-r0" in dockerfile
    assert "ffmpeg=6.1.1-r0" in dockerfile
    assert 'org.opencontainers.image.version="0.7.2-pr117"' in dockerfile
    assert 'io.bella.evolution.patch-revision="0328955"' in dockerfile


def test_evolution_role_guardrails_are_part_of_the_stack_contract() -> None:
    postgres = _load_compose("docker-compose.yml")["services"]["postgres"]

    assert postgres["environment"]["EVOLUTION_DB_CONNECTION_LIMIT"] == (
        f"${{EVOLUTION_DB_CONNECTION_LIMIT:-{ROLE_CONNECTION_LIMIT}}}"
    )
    assert postgres["environment"]["EVOLUTION_DB_IDLE_SESSION_TIMEOUT"] == (
        f"${{EVOLUTION_DB_IDLE_SESSION_TIMEOUT:-{ROLE_IDLE_SESSION_TIMEOUT}}}"
    )


def test_remaining_feature_configuration_is_exposed_to_bella() -> None:
    bella = _load_compose("docker-compose.yml")["services"]["bella"]
    environment = bella["environment"]

    assert environment["ADMIN_CONTACT"].startswith("${ADMIN_CONTACT:")
    assert environment["APOSTILA_PATH"] == (
        "${APOSTILA_PATH:-/app/content/apostila.pdf}"
    )
    assert environment["RATE_LIMIT_MAX_MESSAGES"] == (
        "${RATE_LIMIT_MAX_MESSAGES:-10}"
    )
    assert environment["RATE_LIMIT_WINDOW_SECONDS"] == (
        "${RATE_LIMIT_WINDOW_SECONDS:-60}"
    )
    assert environment["TAKEOVER_PAUSE_SECONDS"] == (
        "${TAKEOVER_PAUSE_SECONDS:-3600}"
    )
    assert "./content:/app/content:ro" in bella["volumes"]


def test_local_overlay_only_publishes_loopback_ports() -> None:
    services = _load_compose("docker-compose.local.yml")["services"]

    for service in services.values():
        assert all(binding.startswith("127.0.0.1:") for binding in service["ports"])


def test_postgres_initializer_is_lf_only_and_creates_all_isolated_databases() -> None:
    script = (ROOT / "deploy/postgres/init-databases.sh").read_bytes()
    text = script.decode("utf-8")

    assert b"\r\n" not in script
    # Shell and Compose cannot import Python; this binds their explicit
    # deployment defaults to the executable policy used by both validators.
    assert (
        f'EVOLUTION_DB_CONNECTION_LIMIT="${{EVOLUTION_DB_CONNECTION_LIMIT:-'
        f'{ROLE_CONNECTION_LIMIT}}}"'
    ) in text
    assert (
        f'EVOLUTION_DB_IDLE_SESSION_TIMEOUT="${{EVOLUTION_DB_IDLE_SESSION_TIMEOUT:-'
        f'{ROLE_IDLE_SESSION_TIMEOUT}}}"'
    ) in text
    assert b"CREATE ROLE bella" in script
    assert b"CREATE ROLE evolution" in script
    assert b"EVOLUTION_DB_CONNECTION_LIMIT" in script
    assert b"EVOLUTION_DB_IDLE_SESSION_TIMEOUT" in script
    assert b"CONNECTION LIMIT" in script
    assert b"NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION" in script
    assert b"ALTER ROLE evolution SET idle_session_timeout" in script
    assert b"idle_in_transaction_session_timeout" not in script
    assert b"max_connections" not in script
    assert b"postgres_password" in script
    assert b"REVOKE CONNECT, TEMPORARY ON DATABASE postgres FROM PUBLIC" in script
    for database in (b"bella", b"evogo_auth", b"evogo_users"):
        assert b"CREATE DATABASE " + database in script


def test_bella_image_uses_immutable_python_and_hash_locked_dependencies() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    lock = (ROOT / "requirements.lock").read_text(encoding="utf-8")

    assert (
        "FROM python:3.12-slim@"
        "sha256:c3d81d25b3154142b0b42eb1e61300024426268edeb5b5a26dd7ddf64d9daf28"
        in dockerfile
    )
    assert (
        "pip install --no-cache-dir --require-hashes "
        "--target /build/deps -r requirements.lock"
    ) in dockerfile
    assert "pip-compile with Python 3.12" in lock
