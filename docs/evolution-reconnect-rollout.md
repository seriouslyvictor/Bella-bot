# Evolution reconnect acceptance and immutable rollout

This runbook turns tickets 04 and 05 into an executable promotion decision.
It does **not** replace the licensed WhatsApp, PostgreSQL, or production work.
The repository tests use synthetic manifests and prove only that the decision
engine rejects unsafe evidence. A passing production assessment is valid only
when an authorized operator performed the steps below and retained the real
artifacts named by the manifest.

Never put database passwords, API keys, license material, full phone numbers,
message contents, or unredacted exports in the evidence directory. Use stable
redacted instance identifiers and message IDs so the before/after records can
still be compared.

## Evidence harness

The harness prints an incomplete, fail-safe template. It never connects to
Evolution, PostgreSQL, Docker, or WhatsApp and never manufactures observations.

```powershell
New-Item -ItemType Directory evidence/reconnect-YYYYMMDD
python -m bella.scripts.evolution_rollout_evidence --template reconnect |
  Set-Content -Encoding utf8 evidence/reconnect-YYYYMMDD/manifest.json
```

Use `--template rollout` for the production manifest. The templates set
`real_evidence` to `false`, leave digests empty, and mark checks incomplete.
Change a field only after the corresponding real check has succeeded.

Evidence artifact paths are relative to the directory containing the manifest.
Every artifact must remain inside that directory and have its lowercase SHA-256
recorded in the manifest. On PowerShell, obtain it with:

```powershell
(Get-FileHash evidence/reconnect-YYYYMMDD/connection-samples.json -Algorithm SHA256).Hash.ToLower()
```

Assess a completed manifest and create a new, non-overwriting decision file:

```powershell
python -m bella.scripts.evolution_rollout_evidence `
  evidence/reconnect-YYYYMMDD/manifest.json `
  --output evidence/reconnect-YYYYMMDD/assessment.json
$LASTEXITCODE
```

Exit `0` and `decision: pass` mean the supplied evidence satisfies the gate.
Exit `1` lists every failed requirement. The assessment includes the canonical
manifest SHA-256 and verified artifact hashes. `--output` refuses to overwrite
an existing assessment; make a new evidence directory for a new run. After the
decision, hash the assessment file itself when a production manifest needs to
refer to that exact ticket-04 run.

## Ticket 04: licensed reconnect acceptance

Run this only on a licensed disposable or staging WhatsApp instance with real
PostgreSQL. Do not use the course owner's production number for fault injection.
Before changing `operator_attestation.real_evidence` to `true`, capture all of
the following preflight facts:

- Source commit is `9337afc47e10b86cc896a6f432240e40fee95dd1`.
- Patch commits are, in order,
  `4cc635dd460f70c36ba83285ecbb34589790572f`,
  `f85ea1445373ea142bb12ba0c01dfc85879be212`, and
  `03289559d547911d92ad58837db98faeb0c5fd8e`.
- Runtime identity is `0.7.2-pr117-0328955`, image reference is
  `bella/evolution-go:0.7.2-pr117-0328955`, and the actual image content digest
  has the form `sha256:<64 lowercase hex>`. Record inspect output, not a tag.
- PostgreSQL reports the `evolution` role as non-superuser with connection
  limit `30`, and a new Evolution session reports role-only
  `idle_session_timeout = 5min`.

Save those checks as `image-identity` evidence. A process-only `/server/ok`
response is useful liveness evidence but is not database-budget evidence.

### Reconnect and sample

1. Capture a `before` session sample.
2. Perform at least 30 starts/reconnects through Evolution's public instance
   behavior. Do not call private functions or edit its database to simulate a
   reconnect.
3. Record one `during` sample for every cycle, numbered contiguously from 1.
   The sample fields are `phase`, `cycle`, `total`, `evogo_auth_total`, and
   `evogo_auth_idle`.
4. Pick the first observed plateau as `plateau_start_cycle`. The harness
   requires at least ten subsequent sampled cycles and rejects any increase in
   total or `evogo_auth` sessions above the first plateau sample.
5. Stop reconnect activity, let the exercise become quiet, and capture an
   `after` sample.

Use the connection-budget command for the raw observation and retain its JSON
output; see [evolution-connection-budget.md](evolution-connection-budget.md).
Convert its groups into the manifest counts without discarding the raw output.
Every sample must keep total Evolution sessions below `24`, keep
`evogo_auth_total` at or below `20`, and the quiet `after` sample must have at
most five idle `evogo_auth` sessions.

Separately, in the disposable environment, fill Evolution sessions to the
24-session warning boundary and prove a Bella-role query still succeeds. Close
those deliberate sessions immediately. Do not continue the reconnect exercise
at the warning boundary.

Review the retained Evolution logs over the exact exercise window. Promotion
is blocked by `too many clients`, unexpected connection refusal, a roughly
two-second database retry storm, pairing loss, API or webhook regression,
timeout failure, or a rising connection trend. `forbidden_errors` may be empty
only after that review. A connection failure intentionally caused by the next
fault-injection step must be time-bounded and identified separately from the
normal reconnect window.

### Recovery and retained behavior

Still in the disposable/staging environment:

1. Make PostgreSQL unavailable before the first authentication-store
   initialization for a fresh test process/instance.
2. Attempt the public connect, restore PostgreSQL, then attempt the public
   connect again **without restarting Evolution**. Record the successful retry.
3. Wait longer than the configured five-minute server-side idle timeout.
   Verify the next Evolution API operation and real WhatsApp message both
   succeed without a user-visible transient failure or operator restart.
4. Verify a real DM receives Bella's reply before and after the reconnect
   exercise.
5. Restart only Evolution and verify the paired instance, license, webhook,
   authentication data, API, and messaging behavior remain intact.
6. Perform a normal unified Compose redeploy and repeat the same state and
   message checks.

Retain these four required artifact kinds with hashes:

- `connection-samples`: raw pre/during/post counts and the separate boundary
  check;
- `evolution-logs`: the complete, time-bounded logs and forbidden-error review;
- `image-identity`: image/source/patch identity and database-role preflight;
- `message-results`: redacted before/after API, state, and real DM results.

Only a passing ticket-04 assessment can be referenced by the production
rollout. A local synthetic fixture is never acceptable for that reference.

## Ticket 05: production rollout

Open a maintenance window and generate a fresh rollout template. Before the
change, record and hash:

- the connection baseline and current budget output;
- verified logical-backup status;
- the running official 0.7.2 image's immutable digest and digest-qualified
  reference;
- redacted instance identity, license state, webhook, and pairing status.

The rollback target must be exactly that pre-change digest. A tag alone, a
mutable registry reference, or a locally remembered image name is rejected.

### Maintenance order

1. Stop **Evolution only**. This clears old leaked sessions and prevents new
   sessions while the retained-volume role policy is reconciled.
2. Reconcile the retained PostgreSQL volume. Verify the Evolution role remains
   non-superuser with limit `30` and role-only timeout `5min`; verify database
   ownership, Bella grants, and persisted data did not change.
3. Deploy the exact patched artifact that passed ticket 04. Record its image
   digest, full deployed repository revision, source/patch revisions, and
   operator-visible runtime identity. Do not rebuild or substitute an artifact
   during promotion.
4. Start Evolution and verify new sessions inherit the role timeout.
5. Verify Manager, license, instance, pairing, webhook, and Evolution API.
6. Send a real DM and retain Bella's reply after deployment, after an
   Evolution-only restart, and after a normal unified-stack redeploy.
7. Confirm the paired instance, Evolution authentication data, Bella
   conversation history, and database ownership/grants survived all three
   checks.
8. Capture at least three ordered connection observations during the window.
   Counts must remain below `24`, `evogo_auth` must remain at or below `20`, and
   `upward_reconnect_trend` must be false.
9. Run the final deployment and contract suites against the deployed revision;
   retain their output before setting `deployment_and_contract_suites_passed`
   to true.

Leave `promotion_blockers` non-empty if any pairing loss, license regression,
API/webhook incompatibility, transient timeout/query error, refusal, retry
storm, rising count, or message failure occurred. The harness will fail closed.

The rollout manifest requires hashed artifacts for `backup-status`,
`pre-change-state`, `post-change-state`, `rollback-rehearsal`, plus the four
ticket-04 evidence categories. Its `reconnect_acceptance.assessment_sha256`
must identify the real passing ticket-04 assessment used for this artifact.

### Immutable emergency rollback

Rehearse this path first in a disposable environment and retain the output:

1. Stop Evolution only.
2. Select the digest-qualified pre-change reference recorded in the rollout
   manifest. Never pull or deploy a floating recovery tag.
3. Keep `CONNECTION LIMIT 30` and the role-only `5min` timeout in place.
4. Start the old image and verify the retained state and messaging surfaces.
5. Mark the rollback as temporary: official 0.7.2 still has the leak. Enable
   active budget monitoring and schedule Evolution-only restarts while it runs.
6. Restore the exact patched image digest and verify it is healthy again.

Do not restart PostgreSQL and do not raise global `max_connections` as leak
responses. At a warning or rising trend, stop reconnect attempts, save the
budget output and Evolution logs, and restart only Evolution. Database restart
would interrupt Bella and other healthy clients without repairing the cause.

## Returning to an official release

Keep `official_release_exit.custom_build_retired` false until all exit criteria
are real. To retire the custom build, the production manifest must additionally
record:

- a released, non-floating official tag and digest-qualified image reference;
- reviewed source evidence that the release contains pull request #117 or an
  equivalent fix;
- a new passing ticket-04 run against that exact digest and its assessment
  SHA-256;
- passing deployment and contract suites; and
- a hashed `official-release-verification` artifact.

Only then set `custom_build_retired` true. Pin the official tag **and** manifest
digest in deployment configuration. The same reconnect, recovery, timeout,
state, and real-message gates apply; upstream release status alone is not an
exit criterion.
