"""Contract tests for the Compose artifact shared by local Docker and Coolify."""

from pathlib import Path
from typing import Any, cast

import yaml


ROOT = Path(__file__).resolve().parent.parent
EVOLUTION_IMAGE = (
    "evoapicloud/evolution-go:0.7.1@"
    "sha256:e1bcb07dea7b130413cf2571b60e11144994fc6a81afdd37a9d2cc4ff67466bf"
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
    assert "./content:/app/content:ro" in bella["volumes"]


def test_local_overlay_only_publishes_loopback_ports() -> None:
    services = _load_compose("docker-compose.local.yml")["services"]

    for service in services.values():
        assert all(binding.startswith("127.0.0.1:") for binding in service["ports"])


def test_postgres_initializer_is_lf_only_and_creates_all_isolated_databases() -> None:
    script = (ROOT / "deploy/postgres/init-databases.sh").read_bytes()

    assert b"\r\n" not in script
    assert b"CREATE ROLE bella" in script
    assert b"CREATE ROLE evolution" in script
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
