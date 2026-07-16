"""Executable acceptance checks for the Evolution reconnect mitigation.

The tests use synthetic manifests. They prove the decision logic only; they
are deliberately not presented as licensed WhatsApp or production evidence.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from bella.scripts.evolution_rollout_evidence import assess_manifest, main


SOURCE_COMMIT = "9337afc47e10b86cc896a6f432240e40fee95dd1"
PATCH_COMMITS = [
    "4cc635dd460f70c36ba83285ecbb34589790572f",
    "f85ea1445373ea142bb12ba0c01dfc85879be212",
    "03289559d547911d92ad58837db98faeb0c5fd8e",
]
PATCHED_DIGEST = f"sha256:{'a' * 64}"


def _artifact(tmp_path: Path, kind: str) -> dict[str, str]:
    path = tmp_path / f"{kind}.txt"
    path.write_text(f"synthetic {kind} fixture\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"kind": kind, "path": path.name, "sha256": digest}


def _ticket04_assessment(
    tmp_path: Path,
    *,
    image_digest: str = PATCHED_DIGEST,
    filename: str = "ticket-04-assessment.json",
    candidate_kind: str = "bella-patched",
) -> dict[str, str]:
    path = tmp_path / filename
    manifest = reconnect_manifest(tmp_path)
    if candidate_kind == "official-release":
        manifest["provenance"] = {
            "candidate_kind": "official-release",
            "release_tag": "0.7.3",
            "source_commit": "1" * 40,
            "image_reference": (
                f"evoapicloud/evolution-go:0.7.3@{image_digest}"
            ),
            "image_digest": image_digest,
            "runtime_identity": "0.7.3",
            "contains_pr117_or_equivalent_fix": True,
            "fix_identity": "upstream-pr-117",
        }
    else:
        manifest["provenance"]["candidate_kind"] = candidate_kind
        manifest["provenance"]["image_digest"] = image_digest
    assessment = assess_manifest(manifest, base_dir=tmp_path)
    path.write_text(json.dumps(assessment, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "assessment_path": path.name,
        "assessment_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def reconnect_manifest(tmp_path: Path) -> dict[str, Any]:
    samples: list[dict[str, Any]] = [
        {
            "phase": "before",
            "cycle": 0,
            "total": 3,
            "evogo_auth_total": 2,
            "evogo_auth_idle": 2,
        }
    ]
    samples.extend(
        {
            "phase": "during",
            "cycle": cycle,
            "total": 8 if cycle < 10 else 9,
            "evogo_auth_total": 6 if cycle < 10 else 7,
            "evogo_auth_idle": 4,
        }
        for cycle in range(1, 31)
    )
    samples.append(
        {
            "phase": "after",
            "cycle": 30,
            "total": 7,
            "evogo_auth_total": 5,
            "evogo_auth_idle": 5,
        }
    )
    return {
        "schema_version": 1,
        "kind": "reconnect-acceptance",
        "environment": "licensed-disposable",
        "operator_attestation": {
            "real_evidence": True,
            "production": False,
        },
        "provenance": {
            "candidate_kind": "bella-patched",
            "source_commit": SOURCE_COMMIT,
            "patch_commits": PATCH_COMMITS,
            "image_reference": "bella/evolution-go:0.7.2-pr117-0328955",
            "image_digest": PATCHED_DIGEST,
            "runtime_identity": "0.7.2-pr117-0328955",
        },
        "database_role": {
            "rolsuper": False,
            "connection_limit": 30,
            "idle_session_timeout": "5min",
        },
        "exercise": {
            "cycles_completed": 30,
            "plateau_start_cycle": 10,
            "samples": samples,
            "forbidden_errors": [],
            "quiet_after_exercise": True,
        },
        "recovery": {
            "postgres_unavailable_on_first_auth_initialization": True,
            "postgres_restored": True,
            "public_connect_retried": True,
            "recovered_without_evolution_restart": True,
            "waited_beyond_role_idle_timeout": True,
            "next_api_operation_succeeded": True,
            "next_whatsapp_message_succeeded": True,
            "bella_query_at_warning_boundary_succeeded": True,
        },
        "state_and_messages": {
            "evolution_restart_preserved_state": True,
            "compose_redeploy_preserved_state": True,
            "paired_instance_preserved": True,
            "license_preserved": True,
            "webhook_preserved": True,
            "authentication_data_preserved": True,
            "manager_compatible": True,
            "api_compatible": True,
            "real_dm_before_succeeded": True,
            "real_dm_after_succeeded": True,
            "real_dm_after_evolution_restart_succeeded": True,
            "real_dm_after_compose_redeploy_succeeded": True,
        },
        "artifacts": [
            _artifact(tmp_path, "connection-samples"),
            _artifact(tmp_path, "evolution-logs"),
            _artifact(tmp_path, "image-identity"),
            _artifact(tmp_path, "message-results"),
        ],
    }


def test_reconnect_manifest_passes_only_with_complete_bounded_evidence(tmp_path: Path) -> None:
    manifest = reconnect_manifest(tmp_path)

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "pass"
    assert assessment["errors"] == []
    assert assessment["evidence_scope"] == "operator-supplied-licensed-environment"
    assert assessment["artifact_sha256"] == {
        artifact["kind"]: artifact["sha256"] for artifact in manifest["artifacts"]
    }
    # The digest lets reviewers bind the decision to the exact input file.
    expected = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert assessment["manifest_sha256"] == expected


def _set_nested(manifest: dict[str, Any], path: str, value: object) -> None:
    parts = path.split(".")
    current = manifest
    for part in parts[:-1]:
        current = current[part]
    current[parts[-1]] = value


def _errors_text(assessment: dict[str, object]) -> str:
    errors = assessment["errors"]
    assert isinstance(errors, list)
    return "\n".join(str(error) for error in errors)


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        ("operator_attestation.real_evidence", False, "real_evidence"),
        ("provenance.source_commit", "0" * 40, "source_commit"),
        ("provenance.patch_commits", list(reversed(PATCH_COMMITS)), "patch_commits"),
        ("provenance.image_reference", "evoapicloud/evolution-go:latest", "image_reference"),
        ("provenance.image_digest", "bella/evolution-go:patched", "image_digest"),
        ("database_role.rolsuper", True, "rolsuper"),
        ("database_role.connection_limit", 31, "connection_limit"),
        ("database_role.idle_session_timeout", "0", "idle_session_timeout"),
        ("exercise.cycles_completed", 29, "at least 30"),
        ("exercise.forbidden_errors", ["too many clients"], "forbidden_errors"),
        (
            "recovery.recovered_without_evolution_restart",
            False,
            "recovered_without_evolution_restart",
        ),
        ("state_and_messages.real_dm_after_succeeded", False, "real_dm_after_succeeded"),
        ("state_and_messages.manager_compatible", False, "manager_compatible"),
    ],
)
def test_reconnect_manifest_rejects_missing_or_unsafe_claims(
    tmp_path: Path, path: str, value: object, error: str
) -> None:
    manifest = deepcopy(reconnect_manifest(tmp_path))
    _set_nested(manifest, path, value)

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert error in _errors_text(assessment)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("total", 24, "below 24"),
        ("evogo_auth_total", 21, "not exceed 20"),
    ],
)
def test_reconnect_manifest_rejects_connection_ceiling_breaches(
    tmp_path: Path, field: str, value: int, error: str
) -> None:
    manifest = reconnect_manifest(tmp_path)
    manifest["exercise"]["samples"][15][field] = value

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert error in _errors_text(assessment)


@pytest.mark.parametrize("field", ["total", "evogo_auth_total", "evogo_auth_idle"])
def test_reconnect_manifest_rejects_negative_connection_counts(
    tmp_path: Path, field: str
) -> None:
    manifest = reconnect_manifest(tmp_path)
    manifest["exercise"]["samples"][15][field] = -1

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert f"{field} cannot be negative" in _errors_text(assessment)


def test_reconnect_manifest_rejects_rising_plateau_and_excess_quiet_idle(
    tmp_path: Path,
) -> None:
    manifest = reconnect_manifest(tmp_path)
    manifest["exercise"]["samples"][30]["total"] = 10
    manifest["exercise"]["samples"][-1]["evogo_auth_idle"] = 6

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    errors = _errors_text(assessment)
    assert assessment["decision"] == "fail"
    assert "increase after plateau_start_cycle" in errors
    assert "more than 5 idle" in errors


def test_reconnect_manifest_rejects_post_plateau_rebound_from_previous_sample(
    tmp_path: Path,
) -> None:
    manifest = reconnect_manifest(tmp_path)
    samples = manifest["exercise"]["samples"]
    samples[10]["total"] = 9
    samples[11]["total"] = 7
    samples[12]["total"] = 8

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "increase after plateau_start_cycle" in _errors_text(assessment)


def test_reconnect_manifest_rejects_tampered_artifact(tmp_path: Path) -> None:
    manifest = reconnect_manifest(tmp_path)
    (tmp_path / "evolution-logs.txt").write_text("changed\n", encoding="utf-8")

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "SHA-256 mismatch" in _errors_text(assessment)


def test_reconnect_manifest_rejects_duplicate_cycle_sample(tmp_path: Path) -> None:
    manifest = reconnect_manifest(tmp_path)
    manifest["exercise"]["samples"].insert(2, manifest["exercise"]["samples"][1])

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "exactly one during sample" in _errors_text(assessment)


def rollout_manifest(tmp_path: Path) -> dict[str, Any]:
    official_digest = f"sha256:{'b' * 64}"
    ticket04 = _ticket04_assessment(tmp_path)
    return {
        "schema_version": 1,
        "kind": "production-rollout",
        "environment": "production",
        "operator_attestation": {"real_evidence": True, "production": True},
        "reconnect_acceptance": {
            "decision": "pass",
            **ticket04,
        },
        "pre_change": {
            "connection_baseline_captured": True,
            "backup_status": "verified",
            "official_image_reference": f"evoapicloud/evolution-go@{official_digest}",
            "official_image_digest": official_digest,
            "instance_identity_recorded": True,
            "license_state_recorded": True,
            "webhook_recorded": True,
            "pairing_status_recorded": True,
        },
        "maintenance": {
            "evolution_stopped_before_role_reconciliation": True,
            "retained_volume_reconciled": True,
            "new_evolution_sessions_verified": True,
        },
        "provenance": {
            "candidate_kind": "bella-patched",
            "source_commit": SOURCE_COMMIT,
            "patch_commits": PATCH_COMMITS,
            "image_reference": "bella/evolution-go:0.7.2-pr117-0328955",
            "image_digest": PATCHED_DIGEST,
            "runtime_identity": "0.7.2-pr117-0328955",
            "repository_revision": "d" * 40,
        },
        "database_role": {
            "rolsuper": False,
            "connection_limit": 30,
            "idle_session_timeout": "5min",
        },
        "post_change": {
            "license_verified": True,
            "instance_verified": True,
            "pairing_verified": True,
            "webhook_verified": True,
            "manager_verified": True,
            "api_verified": True,
            "dm_after_deploy_succeeded": True,
            "dm_after_evolution_restart_succeeded": True,
            "dm_after_compose_redeploy_succeeded": True,
            "paired_instance_preserved": True,
            "authentication_state_preserved": True,
            "bella_conversation_history_preserved": True,
            "database_ownership_and_grants_preserved": True,
            "connection_samples": [
                {"sequence": 1, "total": 9, "evogo_auth_total": 7},
                {"sequence": 2, "total": 10, "evogo_auth_total": 8},
                {"sequence": 3, "total": 9, "evogo_auth_total": 7},
            ],
            "upward_reconnect_trend": False,
            "deployment_and_contract_suites_passed": True,
            "promotion_blockers": [],
        },
        "rollback": {
            "target_reference": f"evoapicloud/evolution-go@{official_digest}",
            "target_digest": official_digest,
            "connection_limit_retained": 30,
            "idle_session_timeout_retained": "5min",
            "known_leaking_target_is_temporary": True,
            "active_connection_monitoring": True,
            "planned_evolution_only_restarts": True,
            "restart_postgres_for_leak": False,
            "raise_global_max_connections": False,
            "rehearsed_in_disposable_environment": True,
            "patched_runtime_restored": True,
            "restored_image_digest": PATCHED_DIGEST,
        },
        "official_release_exit": {
            "custom_build_retired": False,
        },
        "artifacts": [
            _artifact(tmp_path, "connection-samples"),
            _artifact(tmp_path, "evolution-logs"),
            _artifact(tmp_path, "image-identity"),
            _artifact(tmp_path, "message-results"),
            _artifact(tmp_path, "backup-status"),
            _artifact(tmp_path, "pre-change-state"),
            _artifact(tmp_path, "post-change-state"),
            _artifact(tmp_path, "rollback-rehearsal"),
        ],
    }


def test_production_rollout_manifest_passes_with_immutable_recovery_evidence(
    tmp_path: Path,
) -> None:
    assessment = assess_manifest(rollout_manifest(tmp_path), base_dir=tmp_path)

    assert assessment["decision"] == "pass"
    assert assessment["errors"] == []
    assert assessment["evidence_scope"] == "operator-supplied-production"


@pytest.mark.parametrize("candidate_kind", [None, "official-release"])
def test_rollout_rejects_missing_or_wrong_candidate_kind(
    tmp_path: Path, candidate_kind: str | None
) -> None:
    manifest = rollout_manifest(tmp_path)
    if candidate_kind is None:
        del manifest["provenance"]["candidate_kind"]
    else:
        manifest["provenance"]["candidate_kind"] = candidate_kind

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "candidate_kind" in _errors_text(assessment)


def test_rollout_rejects_fabricated_ticket04_assessment_digest(tmp_path: Path) -> None:
    manifest = rollout_manifest(tmp_path)
    manifest["reconnect_acceptance"]["assessment_sha256"] = "c" * 64

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "ticket-04 assessment SHA-256 mismatch" in _errors_text(assessment)


def test_rollout_rejects_nonpassing_ticket04_assessment_file(tmp_path: Path) -> None:
    manifest = rollout_manifest(tmp_path)
    path = tmp_path / manifest["reconnect_acceptance"]["assessment_path"]
    document = json.loads(path.read_text(encoding="utf-8"))
    document["decision"] = "fail"
    path.write_text(json.dumps(document, sort_keys=True) + "\n", encoding="utf-8")
    manifest["reconnect_acceptance"]["assessment_sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "must be a passing reconnect-acceptance" in _errors_text(assessment)


@pytest.mark.parametrize(
    ("path", "value", "error"),
    [
        (
            "pre_change.official_image_reference",
            f"evoapicloud/evolution-go:latest@sha256:{'b' * 64}",
            "never use latest",
        ),
        (
            "maintenance.evolution_stopped_before_role_reconciliation",
            False,
            "evolution_stopped_before_role_reconciliation",
        ),
        ("post_change.upward_reconnect_trend", True, "upward_reconnect_trend"),
        (
            "post_change.deployment_and_contract_suites_passed",
            False,
            "deployment_and_contract_suites_passed",
        ),
        ("post_change.promotion_blockers", ["pairing loss"], "promotion_blockers"),
        ("rollback.target_reference", "evoapicloud/evolution-go:0.7.2", "tag-only"),
        ("rollback.connection_limit_retained", 0, "connection_limit_retained"),
        ("rollback.idle_session_timeout_retained", "0", "idle_session_timeout_retained"),
        ("rollback.known_leaking_target_is_temporary", False, "known_leaking_target"),
        ("rollback.active_connection_monitoring", False, "active_connection_monitoring"),
        ("rollback.planned_evolution_only_restarts", False, "planned_evolution_only"),
        ("rollback.restart_postgres_for_leak", True, "restart_postgres_for_leak"),
        ("rollback.raise_global_max_connections", True, "raise_global_max_connections"),
        ("rollback.restored_image_digest", f"sha256:{'e' * 64}", "restored image"),
    ],
)
def test_rollout_rejects_mutable_or_unsafe_recovery(
    tmp_path: Path, path: str, value: object, error: str
) -> None:
    manifest = rollout_manifest(tmp_path)
    _set_nested(manifest, path, value)

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert error in _errors_text(assessment)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("total", 24, "below 24"),
        ("evogo_auth_total", 21, "not exceed 20"),
    ],
)
def test_rollout_rejects_connection_observation_ceiling_breaches(
    tmp_path: Path, field: str, value: int, error: str
) -> None:
    manifest = rollout_manifest(tmp_path)
    manifest["post_change"]["connection_samples"][1][field] = value

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert error in _errors_text(assessment)


@pytest.mark.parametrize("field", ["total", "evogo_auth_total"])
def test_rollout_rejects_negative_connection_counts(
    tmp_path: Path, field: str
) -> None:
    manifest = rollout_manifest(tmp_path)
    manifest["post_change"]["connection_samples"][1][field] = -1

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert f"{field} cannot be negative" in _errors_text(assessment)


def test_rollout_computes_and_rejects_monotonic_growth(tmp_path: Path) -> None:
    manifest = rollout_manifest(tmp_path)
    manifest["post_change"]["connection_samples"] = [
        {"sequence": 1, "total": 8, "evogo_auth_total": 6},
        {"sequence": 2, "total": 9, "evogo_auth_total": 7},
        {"sequence": 3, "total": 10, "evogo_auth_total": 8},
    ]

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "monotonic growth" in _errors_text(assessment)


def test_custom_build_retirement_requires_verified_official_release(
    tmp_path: Path,
) -> None:
    manifest = rollout_manifest(tmp_path)
    manifest["official_release_exit"] = {"custom_build_retired": True}

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    errors = _errors_text(assessment)
    assert assessment["decision"] == "fail"
    assert "non-floating official release_tag" in errors
    assert "contains_pr117_or_equivalent_fix" in errors
    assert "ticket04_repassed" in errors
    assert "official-release-verification" in errors


def test_custom_build_can_retire_after_official_release_passes_same_gate(
    tmp_path: Path,
) -> None:
    manifest = rollout_manifest(tmp_path)
    digest = f"sha256:{'e' * 64}"
    official_assessment = _ticket04_assessment(
        tmp_path,
        image_digest=digest,
        filename="official-ticket-04-assessment.json",
        candidate_kind="official-release",
    )
    manifest["official_release_exit"] = {
        "custom_build_retired": True,
        "release_tag": "0.7.3",
        "image_reference": f"evoapicloud/evolution-go:0.7.3@{digest}",
        "image_digest": digest,
        "release_source_verified": True,
        "contains_pr117_or_equivalent_fix": True,
        "ticket04_repassed": True,
        "ticket04_assessment_path": official_assessment["assessment_path"],
        "ticket04_assessment_sha256": official_assessment["assessment_sha256"],
        "contract_suites_passed": True,
    }
    manifest["artifacts"].append(_artifact(tmp_path, "official-release-verification"))

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "pass"


def test_official_exit_rejects_patched_provenance_masquerading_as_candidate(
    tmp_path: Path,
) -> None:
    manifest = rollout_manifest(tmp_path)
    digest = f"sha256:{'e' * 64}"
    patched_assessment = _ticket04_assessment(
        tmp_path,
        image_digest=digest,
        filename="masquerading-ticket-04-assessment.json",
    )
    manifest["official_release_exit"] = {
        "custom_build_retired": True,
        "release_tag": "0.7.3",
        "image_reference": f"evoapicloud/evolution-go:0.7.3@{digest}",
        "image_digest": digest,
        "release_source_verified": True,
        "contains_pr117_or_equivalent_fix": True,
        "ticket04_repassed": True,
        "ticket04_assessment_path": patched_assessment["assessment_path"],
        "ticket04_assessment_sha256": patched_assessment["assessment_sha256"],
        "contract_suites_passed": True,
    }
    manifest["artifacts"].append(_artifact(tmp_path, "official-release-verification"))

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "official-release candidate provenance" in _errors_text(assessment)


def test_official_candidate_reconnect_requires_fix_identity(tmp_path: Path) -> None:
    manifest = reconnect_manifest(tmp_path)
    digest = f"sha256:{'e' * 64}"
    manifest["provenance"] = {
        "candidate_kind": "official-release",
        "release_tag": "0.7.3",
        "source_commit": "1" * 40,
        "image_reference": f"evoapicloud/evolution-go:0.7.3@{digest}",
        "image_digest": digest,
        "runtime_identity": "0.7.3",
        "contains_pr117_or_equivalent_fix": True,
        "fix_identity": "",
    }

    assessment = assess_manifest(manifest, base_dir=tmp_path)

    assert assessment["decision"] == "fail"
    assert "fix_identity" in _errors_text(assessment)


def test_cli_writes_new_assessment_and_refuses_to_overwrite_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = tmp_path / "reconnect.json"
    output_path = tmp_path / "assessment.json"
    manifest_path.write_text(
        json.dumps(reconnect_manifest(tmp_path)), encoding="utf-8"
    )

    assert main([str(manifest_path), "--output", str(output_path)]) == 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["decision"] == "pass"
    assert json.loads(capsys.readouterr().out)["decision"] == "pass"
    with pytest.raises(FileExistsError):
        main([str(manifest_path), "--output", str(output_path)])


def test_cli_accepts_utf8_bom_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = tmp_path / "powershell-51-manifest.json"
    encoded = json.dumps(reconnect_manifest(tmp_path)).encode("utf-8")
    manifest_path.write_bytes(b"\xef\xbb\xbf" + encoded)

    assert main([str(manifest_path)]) == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "pass"


@pytest.mark.parametrize(
    ("template", "kind"),
    [
        ("reconnect", "reconnect-acceptance"),
        ("official-reconnect", "reconnect-acceptance"),
        ("rollout", "production-rollout"),
    ],
)
def test_cli_emits_incomplete_templates_without_claiming_real_evidence(
    template: str, kind: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--template", template]) == 0

    document = json.loads(capsys.readouterr().out)
    assert document["kind"] == kind
    assert document["operator_attestation"]["real_evidence"] is False
    if template == "reconnect":
        assert document["provenance"]["candidate_kind"] == "bella-patched"
    if template == "official-reconnect":
        assert document["provenance"]["candidate_kind"] == "official-release"
        assert document["provenance"]["contains_pr117_or_equivalent_fix"] is False
        assert document["provenance"]["fix_identity"] == ""
    if template == "rollout":
        assert document["provenance"]["candidate_kind"] == "bella-patched"
