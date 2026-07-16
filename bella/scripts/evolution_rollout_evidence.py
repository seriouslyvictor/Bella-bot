"""Assess Evolution reconnect and rollout evidence without inventing evidence.

This module deliberately separates deterministic acceptance decisions from the
licensed WhatsApp and production actions that only an operator can perform.
It accepts an operator-populated JSON manifest, verifies its evidence files,
and returns a reviewable pass/fail assessment bound to the exact manifest and
artifact bytes by SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bella.scripts.evolution_connection_policy import (
    AUTH_POOL_CEILING,
    MIN_PLATEAU_SAMPLES,
    MIN_RECONNECT_CYCLES,
    QUIET_AUTH_IDLE_CEILING,
    ROLE_CONNECTION_LIMIT,
    ROLE_IDLE_SESSION_TIMEOUT,
    WARNING_THRESHOLD,
)


SOURCE_COMMIT = "9337afc47e10b86cc896a6f432240e40fee95dd1"
PATCH_COMMITS = [
    "4cc635dd460f70c36ba83285ecbb34589790572f",
    "f85ea1445373ea142bb12ba0c01dfc85879be212",
    "03289559d547911d92ad58837db98faeb0c5fd8e",
]
PATCHED_IDENTITY = "0.7.2-pr117-0328955"
PATCHED_REFERENCE = f"bella/evolution-go:{PATCHED_IDENTITY}"
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _mapping(value: object, name: str, errors: list[str]) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    errors.append(f"{name} must be an object")
    return {}


def _sequence(value: object, name: str, errors: list[str]) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    errors.append(f"{name} must be an array")
    return []


def _require_equal(
    value: object, expected: object, name: str, errors: list[str]
) -> None:
    if value != expected:
        errors.append(f"{name} must be {expected!r}; got {value!r}")


def _require_true(section: Mapping[str, object], names: Sequence[str], errors: list[str]) -> None:
    for name in names:
        if section.get(name) is not True:
            errors.append(f"{name} must be explicitly true")


def _validate_digest(value: object, name: str, errors: list[str]) -> None:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        errors.append(f"{name} must be an immutable sha256:<64 lowercase hex> digest")


def _validate_provenance(manifest: Mapping[str, object], errors: list[str]) -> None:
    provenance = _mapping(manifest.get("provenance"), "provenance", errors)
    _require_equal(provenance.get("source_commit"), SOURCE_COMMIT, "source_commit", errors)
    _require_equal(provenance.get("patch_commits"), PATCH_COMMITS, "patch_commits", errors)
    _require_equal(
        provenance.get("image_reference"), PATCHED_REFERENCE, "image_reference", errors
    )
    _validate_digest(provenance.get("image_digest"), "image_digest", errors)
    _require_equal(
        provenance.get("runtime_identity"), PATCHED_IDENTITY, "runtime_identity", errors
    )


def _validate_role(manifest: Mapping[str, object], errors: list[str]) -> None:
    role = _mapping(manifest.get("database_role"), "database_role", errors)
    _require_equal(role.get("rolsuper"), False, "database_role.rolsuper", errors)
    _require_equal(
        role.get("connection_limit"),
        ROLE_CONNECTION_LIMIT,
        "database_role.connection_limit",
        errors,
    )
    _require_equal(
        role.get("idle_session_timeout"),
        ROLE_IDLE_SESSION_TIMEOUT,
        "database_role.idle_session_timeout",
        errors,
    )


def _integer(value: object, name: str, errors: list[str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{name} must be an integer")
        return None
    return value


@dataclass(frozen=True)
class _ConnectionSample:
    raw: Mapping[str, object]
    total: int | None
    auth_total: int | None
    auth_idle: int | None


def _parse_connection_samples(
    values: Sequence[object],
    name: str,
    errors: list[str],
    *,
    require_idle: bool,
) -> list[_ConnectionSample]:
    """Parse shared count fields and enforce the common policy ceilings."""
    parsed: list[_ConnectionSample] = []
    for index, raw_value in enumerate(values):
        item_name = f"{name}[{index}]"
        sample = _mapping(raw_value, item_name, errors)
        total = _integer(sample.get("total"), f"{item_name}.total", errors)
        auth_total = _integer(
            sample.get("evogo_auth_total"), f"{item_name}.evogo_auth_total", errors
        )
        auth_idle = (
            _integer(
                sample.get("evogo_auth_idle"), f"{item_name}.evogo_auth_idle", errors
            )
            if require_idle
            else None
        )
        if total is not None and total >= WARNING_THRESHOLD:
            errors.append(
                f"{item_name}.total must remain below {WARNING_THRESHOLD}"
            )
        if auth_total is not None and auth_total > AUTH_POOL_CEILING:
            errors.append(
                f"{item_name}.evogo_auth_total must not exceed {AUTH_POOL_CEILING}"
            )
        if auth_idle is not None and auth_idle < 0:
            errors.append(f"{item_name}.evogo_auth_idle cannot be negative")
        parsed.append(_ConnectionSample(sample, total, auth_total, auth_idle))
    return parsed


def _increases(values: Sequence[int | None]) -> bool:
    return all(value is not None for value in values) and any(
        current > previous
        for previous, current in zip(values, values[1:])
        if previous is not None and current is not None
    )


def _validate_samples(exercise: Mapping[str, object], errors: list[str]) -> None:
    cycles = _integer(exercise.get("cycles_completed"), "cycles_completed", errors)
    plateau_start = _integer(
        exercise.get("plateau_start_cycle"), "plateau_start_cycle", errors
    )
    raw_samples = _sequence(exercise.get("samples"), "samples", errors)
    samples = _parse_connection_samples(
        raw_samples, "samples", errors, require_idle=True
    )
    if cycles is None or plateau_start is None:
        return
    if cycles < MIN_RECONNECT_CYCLES:
        errors.append(
            f"cycles_completed must be at least {MIN_RECONNECT_CYCLES}"
        )
    if plateau_start < 1 or plateau_start > cycles - (MIN_PLATEAU_SAMPLES - 1):
        errors.append(
            "plateau_start_cycle must leave at least "
            f"{MIN_PLATEAU_SAMPLES} sampled reconnect cycles"
        )

    by_phase: dict[str, list[_ConnectionSample]] = {
        "before": [],
        "during": [],
        "after": [],
    }
    for index, parsed_sample in enumerate(samples):
        phase = parsed_sample.raw.get("phase")
        if phase not in by_phase:
            errors.append(f"samples[{index}].phase must be before, during, or after")
            continue
        by_phase[str(phase)].append(parsed_sample)

    if len(by_phase["before"]) < 1 or len(by_phase["after"]) < 1:
        errors.append("samples must include before and after phases")

    during_by_cycle: dict[int, _ConnectionSample] = {}
    for during_sample in by_phase["during"]:
        cycle = _integer(
            during_sample.raw.get("cycle"), "during sample cycle", errors
        )
        if cycle is not None:
            during_by_cycle[cycle] = during_sample
    expected_cycles = set(range(1, cycles + 1))
    if set(during_by_cycle) != expected_cycles or len(by_phase["during"]) != cycles:
        errors.append("samples must include exactly one during sample for every reconnect cycle")

    plateau = [during_by_cycle[cycle] for cycle in range(plateau_start, cycles + 1) if cycle in during_by_cycle]
    if len(plateau) >= MIN_PLATEAU_SAMPLES:
        if _increases([plateau_sample.total for plateau_sample in plateau]):
            errors.append("total Evolution sessions increase after plateau_start_cycle")
        if _increases([plateau_sample.auth_total for plateau_sample in plateau]):
            errors.append("evogo_auth sessions increase after plateau_start_cycle")

    for index, after_sample in enumerate(by_phase["after"]):
        idle = after_sample.auth_idle
        if isinstance(idle, int) and idle > QUIET_AUTH_IDLE_CEILING:
            errors.append(
                f"after sample {index} has more than {QUIET_AUTH_IDLE_CEILING} "
                "idle evogo_auth sessions"
            )


def _validate_artifacts(
    manifest: Mapping[str, object],
    base_dir: Path,
    required: set[str],
    errors: list[str],
) -> dict[str, str]:
    verified: dict[str, str] = {}
    base = base_dir.resolve()
    artifacts = _sequence(manifest.get("artifacts"), "artifacts", errors)
    for index, raw_artifact in enumerate(artifacts):
        artifact = _mapping(raw_artifact, f"artifacts[{index}]", errors)
        kind = artifact.get("kind")
        raw_path = artifact.get("path")
        expected = artifact.get("sha256")
        if not isinstance(kind, str) or not kind:
            errors.append(f"artifacts[{index}].kind must be a non-empty string")
            continue
        if kind in verified:
            errors.append(f"artifact kind {kind!r} is duplicated")
            continue
        if not isinstance(raw_path, str) or not raw_path:
            errors.append(f"artifacts[{index}].path must be a non-empty string")
            continue
        if not isinstance(expected, str) or _SHA256.fullmatch(expected) is None:
            errors.append(f"artifacts[{index}].sha256 must be 64 lowercase hex characters")
            continue
        path = (base / raw_path).resolve()
        if not path.is_relative_to(base):
            errors.append(f"artifact {kind!r} must be inside the manifest directory")
            continue
        if not path.is_file():
            errors.append(f"artifact {kind!r} does not exist: {raw_path}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            errors.append(f"artifact {kind!r} SHA-256 mismatch")
            continue
        verified[kind] = actual
    missing = sorted(required - set(verified))
    if missing:
        errors.append(f"missing verified artifacts: {', '.join(missing)}")
    return verified


def _assess_reconnect(
    manifest: Mapping[str, object], base_dir: Path, errors: list[str]
) -> tuple[str, dict[str, str]]:
    environment = manifest.get("environment")
    if environment not in {"licensed-disposable", "licensed-staging"}:
        errors.append("environment must be licensed-disposable or licensed-staging")
    attestation = _mapping(
        manifest.get("operator_attestation"), "operator_attestation", errors
    )
    _require_true(attestation, ["real_evidence"], errors)
    _validate_provenance(manifest, errors)
    _validate_role(manifest, errors)

    exercise = _mapping(manifest.get("exercise"), "exercise", errors)
    _validate_samples(exercise, errors)
    _require_equal(exercise.get("forbidden_errors"), [], "forbidden_errors", errors)
    _require_true(exercise, ["quiet_after_exercise"], errors)

    recovery = _mapping(manifest.get("recovery"), "recovery", errors)
    _require_true(
        recovery,
        [
            "postgres_unavailable_on_first_auth_initialization",
            "postgres_restored",
            "public_connect_retried",
            "recovered_without_evolution_restart",
            "waited_beyond_role_idle_timeout",
            "next_api_operation_succeeded",
            "next_whatsapp_message_succeeded",
            "bella_query_at_warning_boundary_succeeded",
        ],
        errors,
    )
    state = _mapping(
        manifest.get("state_and_messages"), "state_and_messages", errors
    )
    _require_true(
        state,
        [
            "evolution_restart_preserved_state",
            "compose_redeploy_preserved_state",
            "paired_instance_preserved",
            "license_preserved",
            "webhook_preserved",
            "authentication_data_preserved",
            "manager_compatible",
            "api_compatible",
            "real_dm_before_succeeded",
            "real_dm_after_succeeded",
            "real_dm_after_evolution_restart_succeeded",
            "real_dm_after_compose_redeploy_succeeded",
        ],
        errors,
    )
    artifacts = _validate_artifacts(
        manifest,
        base_dir,
        {
            "connection-samples",
            "evolution-logs",
            "image-identity",
            "message-results",
        },
        errors,
    )
    return "operator-supplied-licensed-environment", artifacts


def _validate_pinned_reference(
    reference: object, digest: object, name: str, errors: list[str]
) -> None:
    _validate_digest(digest, f"{name}_digest", errors)
    if not isinstance(reference, str):
        errors.append(f"{name}_reference must be a string pinned by digest")
        return
    if ":latest" in reference.lower() or "@sha256:" not in reference:
        errors.append(f"{name}_reference must be immutable and must never use latest or tag-only")
    if isinstance(digest, str) and not reference.endswith(f"@{digest}"):
        errors.append(f"{name}_reference must end with the recorded digest")


def _validate_rollout_samples(post: Mapping[str, object], errors: list[str]) -> None:
    raw_samples = _sequence(
        post.get("connection_samples"), "connection_samples", errors
    )
    samples = _parse_connection_samples(
        raw_samples, "connection_samples", errors, require_idle=False
    )
    if len(samples) < 3:
        errors.append("connection_samples must cover at least three observation points")
    sequences: list[int] = []
    totals: list[int] = []
    auth_totals: list[int] = []
    for index, sample in enumerate(samples):
        sequence = _integer(
            sample.raw.get("sequence"),
            f"connection_samples[{index}].sequence",
            errors,
        )
        if sequence is not None:
            sequences.append(sequence)
        if sample.total is not None:
            totals.append(sample.total)
        if sample.auth_total is not None:
            auth_totals.append(sample.auth_total)
    if sequences != list(range(1, len(samples) + 1)):
        errors.append("connection_samples sequence must be contiguous and ordered from 1")
    if len(totals) > 1 and all(
        current > previous for previous, current in zip(totals, totals[1:])
    ):
        errors.append("connection_samples show monotonic growth in total Evolution sessions")
    if len(auth_totals) > 1 and all(
        current > previous
        for previous, current in zip(auth_totals, auth_totals[1:])
    ):
        errors.append("connection_samples show monotonic growth in evogo_auth sessions")
    _require_equal(post.get("upward_reconnect_trend"), False, "upward_reconnect_trend", errors)


def _validate_ticket04_assessment(
    section: Mapping[str, object],
    *,
    path_field: str,
    digest_field: str,
    expected_image_digest: object,
    base_dir: Path,
    errors: list[str],
) -> None:
    """Verify a byte-bound, passing ticket-04 assessment for the right image."""
    raw_path = section.get(path_field)
    expected_digest = section.get(digest_field)
    label = "ticket-04 assessment"
    if not isinstance(raw_path, str) or not raw_path:
        errors.append(f"{path_field} must identify the actual {label} file")
        return
    if not isinstance(expected_digest, str) or _SHA256.fullmatch(expected_digest) is None:
        errors.append(f"{digest_field} must be 64 lowercase hex")
        return

    base = base_dir.resolve()
    path = (base / raw_path).resolve()
    if not path.is_relative_to(base):
        errors.append(f"{label} must be inside the manifest directory")
        return
    if not path.is_file():
        errors.append(f"{label} does not exist: {raw_path}")
        return
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        errors.append(f"{label} SHA-256 mismatch")
        return
    try:
        assessment = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        errors.append(f"{label} must be valid UTF-8 JSON")
        return
    document = _mapping(assessment, label, errors)
    required_artifacts = {
        "connection-samples",
        "evolution-logs",
        "image-identity",
        "message-results",
    }
    artifact_hashes = document.get("artifact_sha256")
    artifact_hashes_valid = isinstance(artifact_hashes, Mapping) and all(
        isinstance(artifact_hashes.get(kind), str)
        and _SHA256.fullmatch(str(artifact_hashes.get(kind))) is not None
        for kind in required_artifacts
    )
    manifest_digest = document.get("manifest_sha256")
    if not (
        document.get("schema_version") == 1
        and document.get("kind") == "reconnect-acceptance"
        and document.get("decision") == "pass"
        and document.get("errors") == []
        and document.get("evidence_scope")
        == "operator-supplied-licensed-environment"
        and isinstance(manifest_digest, str)
        and _SHA256.fullmatch(manifest_digest) is not None
        and artifact_hashes_valid
    ):
        errors.append(f"{label} must be a passing reconnect-acceptance assessment")
    if document.get("subject_image_digest") != expected_image_digest:
        errors.append(f"{label} must assess the image digest being deployed")


def _validate_official_exit(
    manifest: Mapping[str, object],
    base_dir: Path,
    artifacts_required: set[str],
    errors: list[str],
) -> None:
    official = _mapping(
        manifest.get("official_release_exit"), "official_release_exit", errors
    )
    retired = official.get("custom_build_retired")
    if retired is False:
        return
    if retired is not True:
        errors.append("custom_build_retired must be explicitly true or false")
        return
    tag = official.get("release_tag")
    if not isinstance(tag, str) or not tag or tag.lower() == "latest":
        errors.append("retirement requires a non-floating official release_tag")
    _validate_pinned_reference(
        official.get("image_reference"),
        official.get("image_digest"),
        "official_release_image",
        errors,
    )
    _require_true(
        official,
        [
            "release_source_verified",
            "contains_pr117_or_equivalent_fix",
            "ticket04_repassed",
            "contract_suites_passed",
        ],
        errors,
    )
    _validate_ticket04_assessment(
        official,
        path_field="ticket04_assessment_path",
        digest_field="ticket04_assessment_sha256",
        expected_image_digest=official.get("image_digest"),
        base_dir=base_dir,
        errors=errors,
    )
    artifacts_required.add("official-release-verification")


def _assess_rollout(
    manifest: Mapping[str, object], base_dir: Path, errors: list[str]
) -> tuple[str, dict[str, str]]:
    _require_equal(manifest.get("environment"), "production", "environment", errors)
    attestation = _mapping(
        manifest.get("operator_attestation"), "operator_attestation", errors
    )
    _require_true(attestation, ["real_evidence", "production"], errors)

    acceptance = _mapping(
        manifest.get("reconnect_acceptance"), "reconnect_acceptance", errors
    )
    _require_equal(acceptance.get("decision"), "pass", "reconnect_acceptance.decision", errors)
    provenance_for_acceptance = _mapping(manifest.get("provenance"), "provenance", errors)
    _validate_ticket04_assessment(
        acceptance,
        path_field="assessment_path",
        digest_field="assessment_sha256",
        expected_image_digest=provenance_for_acceptance.get("image_digest"),
        base_dir=base_dir,
        errors=errors,
    )

    pre = _mapping(manifest.get("pre_change"), "pre_change", errors)
    _require_true(
        pre,
        [
            "connection_baseline_captured",
            "instance_identity_recorded",
            "license_state_recorded",
            "webhook_recorded",
            "pairing_status_recorded",
        ],
        errors,
    )
    _require_equal(pre.get("backup_status"), "verified", "backup_status", errors)
    _validate_pinned_reference(
        pre.get("official_image_reference"),
        pre.get("official_image_digest"),
        "official_image",
        errors,
    )

    maintenance = _mapping(manifest.get("maintenance"), "maintenance", errors)
    _require_true(
        maintenance,
        [
            "evolution_stopped_before_role_reconciliation",
            "retained_volume_reconciled",
            "new_evolution_sessions_verified",
        ],
        errors,
    )
    _validate_provenance(manifest, errors)
    provenance = _mapping(manifest.get("provenance"), "provenance", errors)
    revision = provenance.get("repository_revision")
    if not isinstance(revision, str) or _COMMIT.fullmatch(revision) is None:
        errors.append("repository_revision must be a full 40-character commit")
    if provenance.get("image_digest") == pre.get("official_image_digest"):
        errors.append("pre-change and patched image digests must identify different artifacts")
    _validate_role(manifest, errors)

    post = _mapping(manifest.get("post_change"), "post_change", errors)
    _require_true(
        post,
        [
            "license_verified",
            "instance_verified",
            "pairing_verified",
            "webhook_verified",
            "manager_verified",
            "api_verified",
            "dm_after_deploy_succeeded",
            "dm_after_evolution_restart_succeeded",
            "dm_after_compose_redeploy_succeeded",
            "paired_instance_preserved",
            "authentication_state_preserved",
            "bella_conversation_history_preserved",
            "database_ownership_and_grants_preserved",
            "deployment_and_contract_suites_passed",
        ],
        errors,
    )
    _validate_rollout_samples(post, errors)
    _require_equal(post.get("promotion_blockers"), [], "promotion_blockers", errors)

    rollback = _mapping(manifest.get("rollback"), "rollback", errors)
    _validate_pinned_reference(
        rollback.get("target_reference"),
        rollback.get("target_digest"),
        "rollback_target",
        errors,
    )
    _require_equal(
        rollback.get("target_digest"),
        pre.get("official_image_digest"),
        "rollback target versus pre-change digest",
        errors,
    )
    _require_equal(
        rollback.get("connection_limit_retained"),
        30,
        "rollback.connection_limit_retained",
        errors,
    )
    _require_equal(
        rollback.get("idle_session_timeout_retained"),
        "5min",
        "rollback.idle_session_timeout_retained",
        errors,
    )
    _require_true(
        rollback,
        [
            "known_leaking_target_is_temporary",
            "active_connection_monitoring",
            "planned_evolution_only_restarts",
            "rehearsed_in_disposable_environment",
            "patched_runtime_restored",
        ],
        errors,
    )
    _require_equal(
        rollback.get("restart_postgres_for_leak"),
        False,
        "rollback.restart_postgres_for_leak",
        errors,
    )
    _require_equal(
        rollback.get("raise_global_max_connections"),
        False,
        "rollback.raise_global_max_connections",
        errors,
    )
    _require_equal(
        rollback.get("restored_image_digest"),
        provenance.get("image_digest"),
        "rollback restored image versus deployed patched image",
        errors,
    )

    required_artifacts = {
        "connection-samples",
        "evolution-logs",
        "image-identity",
        "message-results",
        "backup-status",
        "pre-change-state",
        "post-change-state",
        "rollback-rehearsal",
    }
    _validate_official_exit(manifest, base_dir, required_artifacts, errors)
    artifacts = _validate_artifacts(manifest, base_dir, required_artifacts, errors)
    return "operator-supplied-production", artifacts


def assess_manifest(manifest: Mapping[str, object], *, base_dir: Path) -> dict[str, object]:
    """Return a deterministic assessment for an operator evidence manifest."""

    errors: list[str] = []
    _require_equal(manifest.get("schema_version"), 1, "schema_version", errors)
    kind = manifest.get("kind")
    if kind == "reconnect-acceptance":
        evidence_scope, artifacts = _assess_reconnect(manifest, base_dir, errors)
    elif kind == "production-rollout":
        evidence_scope, artifacts = _assess_rollout(manifest, base_dir, errors)
    else:
        evidence_scope = "unknown"
        artifacts = {}
        errors.append("kind must be reconnect-acceptance or production-rollout")
    return {
        "schema_version": 1,
        "kind": kind,
        "decision": "fail" if errors else "pass",
        "evidence_scope": evidence_scope,
        "subject_image_digest": _mapping(
            manifest.get("provenance"), "assessment provenance", []
        ).get("image_digest"),
        "manifest_sha256": _canonical_sha256(manifest),
        "artifact_sha256": artifacts,
        "errors": errors,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assess operator-supplied Evolution reconnect/rollout evidence."
    )
    parser.add_argument("manifest", nargs="?", type=Path, help="JSON evidence manifest")
    parser.add_argument(
        "--template",
        choices=("reconnect", "rollout"),
        help="print an explicitly incomplete evidence manifest template",
    )
    parser.add_argument(
        "--output", type=Path, help="write the assessment JSON to this new file"
    )
    return parser


def _artifact_templates(kinds: Sequence[str]) -> list[dict[str, str]]:
    return [{"kind": kind, "path": "", "sha256": ""} for kind in kinds]


def _template(name: str) -> dict[str, object]:
    provenance: dict[str, object] = {
        "source_commit": SOURCE_COMMIT,
        "patch_commits": PATCH_COMMITS,
        "image_reference": PATCHED_REFERENCE,
        "image_digest": "",
        "runtime_identity": PATCHED_IDENTITY,
    }
    role: dict[str, object] = {
        "rolsuper": None,
        "connection_limit": None,
        "idle_session_timeout": "",
    }
    if name == "reconnect":
        return {
            "schema_version": 1,
            "kind": "reconnect-acceptance",
            "environment": "licensed-disposable-or-staging",
            "operator_attestation": {"real_evidence": False, "production": False},
            "provenance": provenance,
            "database_role": role,
            "exercise": {
                "cycles_completed": 0,
                "plateau_start_cycle": 0,
                "samples": [],
                "forbidden_errors": ["NOT REVIEWED"],
                "quiet_after_exercise": False,
            },
            "recovery": {
                "postgres_unavailable_on_first_auth_initialization": False,
                "postgres_restored": False,
                "public_connect_retried": False,
                "recovered_without_evolution_restart": False,
                "waited_beyond_role_idle_timeout": False,
                "next_api_operation_succeeded": False,
                "next_whatsapp_message_succeeded": False,
                "bella_query_at_warning_boundary_succeeded": False,
            },
            "state_and_messages": {
                "evolution_restart_preserved_state": False,
                "compose_redeploy_preserved_state": False,
                "paired_instance_preserved": False,
                "license_preserved": False,
                "webhook_preserved": False,
                "authentication_data_preserved": False,
                "manager_compatible": False,
                "api_compatible": False,
                "real_dm_before_succeeded": False,
                "real_dm_after_succeeded": False,
                "real_dm_after_evolution_restart_succeeded": False,
                "real_dm_after_compose_redeploy_succeeded": False,
            },
            "artifacts": _artifact_templates(
                [
                    "connection-samples",
                    "evolution-logs",
                    "image-identity",
                    "message-results",
                ]
            ),
        }
    provenance["repository_revision"] = ""
    return {
        "schema_version": 1,
        "kind": "production-rollout",
        "environment": "production",
        "operator_attestation": {"real_evidence": False, "production": False},
        "reconnect_acceptance": {
            "decision": "not-run",
            "assessment_path": "",
            "assessment_sha256": "",
        },
        "pre_change": {
            "connection_baseline_captured": False,
            "backup_status": "not-verified",
            "official_image_reference": "",
            "official_image_digest": "",
            "instance_identity_recorded": False,
            "license_state_recorded": False,
            "webhook_recorded": False,
            "pairing_status_recorded": False,
        },
        "maintenance": {
            "evolution_stopped_before_role_reconciliation": False,
            "retained_volume_reconciled": False,
            "new_evolution_sessions_verified": False,
        },
        "provenance": provenance,
        "database_role": role,
        "post_change": {
            "license_verified": False,
            "instance_verified": False,
            "pairing_verified": False,
            "webhook_verified": False,
            "manager_verified": False,
            "api_verified": False,
            "dm_after_deploy_succeeded": False,
            "dm_after_evolution_restart_succeeded": False,
            "dm_after_compose_redeploy_succeeded": False,
            "paired_instance_preserved": False,
            "authentication_state_preserved": False,
            "bella_conversation_history_preserved": False,
            "database_ownership_and_grants_preserved": False,
            "connection_samples": [],
            "upward_reconnect_trend": None,
            "deployment_and_contract_suites_passed": False,
            "promotion_blockers": ["NOT REVIEWED"],
        },
        "rollback": {
            "target_reference": "",
            "target_digest": "",
            "connection_limit_retained": None,
            "idle_session_timeout_retained": "",
            "known_leaking_target_is_temporary": False,
            "active_connection_monitoring": False,
            "planned_evolution_only_restarts": False,
            "restart_postgres_for_leak": True,
            "raise_global_max_connections": True,
            "rehearsed_in_disposable_environment": False,
            "patched_runtime_restored": False,
            "restored_image_digest": "",
        },
        "official_release_exit": {"custom_build_retired": False},
        "artifacts": _artifact_templates(
            [
                "connection-samples",
                "evolution-logs",
                "image-identity",
                "message-results",
                "backup-status",
                "pre-change-state",
                "post-change-state",
                "rollback-rehearsal",
            ]
        ),
    }


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. A failed assessment returns exit status 1."""

    parser = _parser()
    args = parser.parse_args(argv)
    if args.template is not None:
        if args.manifest is not None or args.output is not None:
            parser.error("--template cannot be combined with a manifest or --output")
        print(json.dumps(_template(str(args.template)), indent=2, sort_keys=True))
        return 0
    if args.manifest is None:
        parser.error("a manifest path or --template is required")
    manifest_path: Path = args.manifest
    raw: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise SystemExit("manifest root must be a JSON object")
    assessment = assess_manifest(raw, base_dir=manifest_path.parent)
    rendered = json.dumps(assessment, indent=2, sort_keys=True) + "\n"
    output: Path | None = args.output
    if output is not None:
        # Refuse to overwrite a prior signed-off decision accidentally.
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(rendered)
    print(rendered, end="")
    return 0 if assessment["decision"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
