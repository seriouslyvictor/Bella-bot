# Spec: Contain Evolution GO 0.7.2 PostgreSQL Connection Leaks

Status: ready-for-agent

## Problem Statement

Bella's operator had to move away from Evolution GO 0.7.1 after runtime problems and recover by pulling the floating `latest` image. As of 2026-07-16, `latest` resolves to the official 0.7.2 build, which contains the open PostgreSQL connection leak reported in upstream issues #106 and #109. It does not contain the open, unmerged fix in pull request #117.

Evolution GO 0.7.2 creates a new WhatsMeow authentication-store connection pool every time a client starts or reconnects. Those pools have no open-connection cap or connection lifetime and are not closed. QR expiry, network instability, startup connection attempts, manual reconnects, or an internal retry loop can therefore leave an increasing number of idle sessions in `evogo_auth`. Once PostgreSQL reaches `max_connections`, Evolution enters a retry storm and the shared PostgreSQL service can also reject Bella's otherwise healthy database connections.

The current unified stack has no Evolution-specific connection budget, idle-session reclamation, or continuous leak signal. Evolution's `/server/ok` health endpoint only proves that its HTTP process is alive, and Docker/Coolify does not restart a merely unhealthy process. The local switch to `latest` also contradicts the repository's existing immutable-image contract, tests, deployment guide, and Bella Bot v1 spec, so the deployed binary is no longer reproducible from the repository.

## Solution

Ship a temporary Bella-owned Evolution GO 0.7.2 build containing only the three commits from upstream pull request #117. Build it from the exact 0.7.2 source revision using pinned, checksummed inputs; give it an explicit `0.7.2-pr117` identity; and deploy it through the same unified Compose stack instead of using `latest`. Preserve the upstream fix's behavior: one shared authentication-store container, at most 20 open and 5 idle PostgreSQL connections, a five-minute maximum connection lifetime, a two-minute maximum idle time, and retryable initialization failures.

Add a second containment layer at PostgreSQL. Keep Evolution on its existing dedicated, non-superuser `evolution` role, limit that role to 30 concurrent connections across its databases, and apply a role-only five-minute `idle_session_timeout`. This leaves capacity for Bella's separate role and the PostgreSQL administrator even if Evolution regresses. Make both guardrails part of idempotent database reconciliation so fresh and retained volumes receive the same policy.

Add an operator connection-budget check based on `pg_stat_activity`. For the current one-instance topology, 24 Evolution sessions is the warning threshold. A count at or above that threshold, or a count that rises with successive reconnects instead of reaching a plateau, requires stopping further reconnect attempts and restarting only Evolution GO to release its pools. Raising PostgreSQL's global `max_connections` is not a fix.

Retire the custom build only after an official Evolution GO release demonstrably contains the equivalent fix and passes the same connection-lifecycle tests. That official release must then be pinned by version and manifest digest; `latest` must not return.

## User Stories

1. As a prospective student, I want Bella to keep replying even when Evolution GO has reconnected several times, so that an infrastructure leak does not make the course concierge disappear.
2. As a prospective student, I want my message and Bella's reply to survive an Evolution GO maintenance restart, so that operational recovery does not lose the conversation.
3. As a course owner, I want Evolution GO failures contained to Evolution's database role, so that Bella's conversation history remains available.
4. As a course owner, I want the paired WhatsApp instance, webhook, license state, and authentication data preserved across the mitigation rollout, so that the number does not need to be re-paired unnecessarily.
5. As an operator, I want the deployed Evolution GO source and patch revisions to be explicit, so that I know exactly which leak fix is running.
6. As an operator, I want every remote build input and base image pinned, so that rebuilding the same repository revision cannot silently produce a different Evolution binary.
7. As an operator, I want the unified stack to stop using `latest`, so that a registry push cannot change production during an unrelated redeploy.
8. As an operator, I want Evolution GO to reuse one bounded authentication-store pool, so that reconnect count no longer determines database connection count.
9. As an operator, I want a failed first database initialization to be retried later, so that a brief PostgreSQL startup delay does not poison Evolution until the next container restart.
10. As an operator, I want Evolution's database role capped independently of Bella's role, so that a future Evolution regression cannot consume every normal PostgreSQL connection.
11. As an operator, I want leaked idle Evolution sessions reclaimed without applying a cluster-wide timeout, so that Bella and administrative sessions keep their normal behavior.
12. As an operator, I want the connection cap and timeout applied to both fresh and retained PostgreSQL volumes, so that production does not keep unsafe role defaults merely because its volume already exists.
13. As an operator, I want existing Evolution sessions cleared during rollout, so that connections leaked before the guardrail was applied do not remain until the next incident.
14. As an operator, I want to see Evolution connection counts grouped by database and state, so that normal pool activity is distinguishable from a growing idle leak.
15. As an operator, I want a concrete warning threshold and response, so that I do not have to improvise while PostgreSQL is approaching exhaustion.
16. As an operator, I want recovery to restart Evolution GO rather than PostgreSQL, so that Bella's database and other healthy clients are not interrupted unnecessarily.
17. As an operator, I want the stack to reject an unsafe rollout when connection counts rise across repeated reconnects, so that the connection cap is not mistaken for proof that the leak was fixed.
18. As an operator, I want the patched image to retain Evolution GO 0.7.2's current API, Manager, licensing, database, and webhook behavior, so that solving the leak does not revive the problems that forced the 0.7.1 rollback.
19. As an operator, I want an emergency rollback image recorded by immutable identity, so that rollback never means pulling whatever `latest` happens to contain.
20. As an operator, I want the server-side timeout tested against Evolution's pool before production, so that unexpected connection closure does not create a new message-delivery failure.
21. As a developer, I want the upstream regression test to run against the backport, so that failed initialization remains retryable and successful initialization returns the same shared container.
22. As a developer, I want deployment contract tests to reject floating Evolution images and missing role guardrails, so that the mitigation cannot be accidentally removed in a routine Compose edit.
23. As a developer, I want the leak exercised through Evolution's public connect/reconnect behavior and a real PostgreSQL server, so that tests observe the production failure mode rather than private implementation details alone.
24. As a maintainer, I want the Bella-specific patch kept minimal and traceable to upstream commits, so that it is easy to review and later delete.
25. As a maintainer, I want a defined exit condition for returning to an official Evolution image, so that Bella does not own a permanent fork by accident.
26. As a maintainer, I want any future increase in the number of Evolution instances to trigger a new measured connection budget, so that the one-instance limit is not scaled by guesswork.

## Implementation Decisions

### Temporary Evolution GO build

- Use upstream Evolution GO 0.7.2 source commit `9337afc47e10b86cc896a6f432240e40fee95dd1`, the commit referenced by the 0.7.2 release tag, as the only base. Do not build the pull-request branch wholesale and do not pull `develop`.
- Apply the three pull-request commits in order: `4cc635dd460f70c36ba83285ecbb34589790572f`, `f85ea1445373ea142bb12ba0c01dfc85879be212`, and `03289559d547911d92ad58837db98faeb0c5fd8e`. The build must fail if the patch no longer applies exactly.
- Keep a reviewed copy of the three-commit patch as a repository build input. Production builds must not depend on the continued existence or mutable head of an open pull-request branch.
- Preserve the fix values from pull request #117: one process-wide authentication-store container; PostgreSQL maximums of 20 open and 5 idle connections; five-minute connection lifetime; two-minute idle lifetime; SQLite maximum of one connection; close the database after initialization failure; and memoize only successful initialization.
- Add no unrelated upstream changes. The custom build is a backport, not a general fork or upgrade channel.
- Build Evolution GO within the unified Compose project, as Bella is already built there, and assign the non-floating local image identity `bella/evolution-go:0.7.2-pr117-0328955`. Pin build-stage and runtime base images by digest and verify any fetched source archive by checksum.
- Record the produced image digest in the deployment evidence. If an authenticated registry is later selected, publish this exact artifact and replace the local image identity with its manifest digest without changing the source inputs.
- Expose the patched identity in image metadata and operator output so production can be distinguished from official 0.7.2 without reading source code.
- The temporary source build supersedes the Bella Bot v1 requirement to run the official 0.7.1 digest. It does not supersede the broader requirement for explicit, reproducible runtime inputs.

### PostgreSQL containment

- Continue using the dedicated `evolution` login role for `evogo_auth`, `evogo_users`, and Evolution's startup check against the maintenance database. The role must remain non-superuser because PostgreSQL does not enforce role connection limits for superusers.
- Set the current one-instance role budget to `CONNECTION LIMIT 30`. This covers the patched auth pool's 20-connection ceiling plus the users database, startup/health checks, and measured headroom while reserving most of the PostgreSQL 15 cluster for Bella and administration.
- Set `idle_session_timeout` to five minutes for the `evolution` role only. Do not apply it globally and do not change Bella's role defaults. This is a circuit breaker for a future leaked idle pool, not the primary fix.
- Leave `idle_in_transaction_session_timeout` and the cluster-wide `max_connections` unchanged for this effort. The observed leak is ordinary `idle`, not `idle in transaction`, and increasing the global limit only delays exhaustion.
- Pass the role budget and idle timeout through the stack's environment contract with defaults of `30` and `5min`, validate them before interpolation into SQL, and document that changing either value is a capacity decision requiring the reconnect test.
- Extend the idempotent database initializer to reconcile the role attributes as well as its password and grants. On retained volumes, operators must rerun reconciliation explicitly because the official PostgreSQL entrypoint does not rerun initialization scripts.
- Apply the role policy while Evolution is stopped, then start the patched image. A restart is mandatory so all pre-existing leaked sessions are closed and all new sessions inherit the role timeout.
- Keep `DATABASE_SAVE_MESSAGES=false`; it reduces stored message data but does not bypass the WhatsMeow authentication store and is not a leak mitigation.

### Observation and incident response

- Provide one operator check that reports the `evolution` role's sessions grouped by database, state, and application/client identity, plus total Evolution sessions and the configured role limit.
- Treat 24 concurrent Evolution sessions, 80% of the 30-session budget, as a warning for the current topology. Also treat monotonic growth across reconnect cycles as a failure even when the absolute count is below 24.
- At the warning threshold, stop manual or automated reconnect attempts, capture connection and Evolution logs, and restart only Evolution GO. Do not restart PostgreSQL and do not raise `max_connections` as an incident response.
- Keep the existing HTTP liveness checks, but do not present `/server/ok` as proof of database health. The connection-budget check belongs in deployment verification and operational monitoring.
- Do not mount the Docker socket or grant a watchdog container control of the host. Automated restart orchestration can be added later through an approved Coolify/host mechanism; the initial circuit breaker is a documented operator action.

### Rollout, rollback, and exit

- Roll out in a maintenance window: capture a connection baseline and logical backup status, stop Evolution, reconcile the role policy, deploy the patched build, verify license/instance/webhook state, and send a real WhatsApp message in both directions.
- Keep the exact pre-change 0.7.2 image digest recorded for emergency rollback; never use `latest` as a rollback target. Because official 0.7.2 contains the leak, such a rollback is temporary, keeps both PostgreSQL guardrails, and requires active connection monitoring and planned Evolution restarts.
- Promotion is blocked by any pairing loss, license regression, webhook/API incompatibility, transient query failures caused by the role timeout, connection refusal, retry storm, or connection count that scales with reconnect attempts.
- Return to an official Evolution image only after a released tag contains pull request #117 or an equivalent reviewed fix. Verify the release source, rerun this spec's tests, and pin the official tag and manifest digest before deleting the custom build.

## Testing Decisions

- A good test observes externally meaningful behavior: the deployed image identity, successful instance startup and messaging, stable PostgreSQL session counts across reconnects, recovery after an idle timeout, retained state after redeploy, and Bella's continued database access. Tests should not pass merely because a particular mutex, singleton variable, or source-file shape exists.
- The primary automated seam is the existing unified Compose contract suite. Extend it to reject `latest`, require the explicit patched build identity and pinned inputs, require the role-budget environment contract, and preserve the existing service topology, isolated database roles, health checks, and production port restrictions.
- Extend the existing database-initializer contract test to prove that the Evolution role receives the connection limit and role-only timeout and that the initializer remains LF-only, idempotent, and safe for fresh and retained volumes.
- Run the upstream regression test included by pull request #117 against the backported 0.7.2 source. It must prove that a failed first store initialization is not cached and that calls after a successful initialization return the same container.
- Build the custom image from an empty cache at least once. Verify its source revision, patch revision, version metadata, target architecture, and runtime health before using Compose-level cache.
- On a disposable PostgreSQL volume, verify the role is non-superuser, has a connection limit of 30, and receives the five-minute timeout on new sessions. Open sessions up to the role limit and prove that an additional Evolution-role session is rejected while a Bella-role query and an administrator query still succeed; then close all test sessions.
- Repeat role reconciliation against a retained disposable volume and prove the attributes change without recreating databases, changing owners, losing WhatsApp auth tables, or altering Bella's grants.
- Use a licensed, disposable or staging WhatsApp instance and Evolution's public connect/reconnect behavior to perform at least 30 start/reconnect cycles. Sample `pg_stat_activity` before, during, and after the sequence. The count must plateau rather than rise with cycle number, `evogo_auth` must never exceed the 20-open-connection pool ceiling, the total Evolution count must remain below the 24-session warning threshold, and no `too many clients` or two-second database retry storm may appear.
- After the reconnect exercise is quiet, no more than five idle `evogo_auth` sessions may remain. Wait beyond the configured server idle timeout, then exercise the API again and prove that the connection pool recovers without a failed message or operator restart.
- Simulate PostgreSQL being unavailable during the first auth-container initialization, restore it, and retry through the public instance boundary. Evolution must recover without a process restart, demonstrating the second and third pull-request commits.
- Send a real WhatsApp DM before the rollout, after the patched deployment, after an Evolution-only restart, and after a normal Compose redeploy. Bella must receive and reply, and the existing instance, pairing, webhook, and database state must remain intact.
- During the runtime exercise, verify Bella's own PostgreSQL query succeeds while Evolution is at its warning threshold. This is the behavior that proves the shared cluster's blast radius is contained.
- Exercise the immutable emergency rollback procedure once in a disposable environment, verify that the PostgreSQL guardrails remain applied, then restore the patched build. Do not promote the known-leaking rollback image to normal operation.
- Prior art is the repository's Compose artifact contract tests, idempotent PostgreSQL initializer tests, real-PostgreSQL conversation-store integration tests, and the full-stack operational checks recorded for the original unified deployment.

## Out of Scope

- Diagnosing or repairing the separate Evolution GO 0.7.1 runtime problems that forced the move to 0.7.2.
- Waiting for, approving, or merging upstream pull request #117.
- Maintaining a permanent Bella fork of Evolution GO or taking unrelated upstream changes.
- Increasing PostgreSQL's global `max_connections` as a capacity workaround.
- Adding PgBouncer. It can cap PostgreSQL backend sessions but does not remove the leaked Evolution-to-PgBouncer clients and introduces a new transaction/prepared-statement compatibility seam.
- Splitting Evolution and Bella onto separate PostgreSQL servers. The existing isolated-role boundary is sufficient once the role budget is enforced.
- Changing Bella's bounded conversation-store pool, schema, Knowledge Base, Scope Gate, message pipeline, or retention behavior.
- Supporting multiple active Evolution instances without a new measured role budget and reconnect test.
- Granting an in-stack watchdog Docker-socket or host-control privileges.

## Further Notes

- Upstream issue #109 is open and documents 0.7.2 exhausting PostgreSQL while 0.7.1 remained at three idle sessions under the reporter's comparison: <https://github.com/evolution-foundation/evolution-go/issues/109>.
- Issue #106 independently reports one additional pool per retry and connections falling from 167 to 3 after an Evolution container restart: <https://github.com/evolution-foundation/evolution-go/issues/106>.
- Pull request #117 is open and unmerged as of 2026-07-16, with no maintainer approval or substantive upstream CI result: <https://github.com/evolution-foundation/evolution-go/pull/117>.
- Official `latest` and `0.7.2` currently resolve to the same per-architecture Docker Hub image content, both published before the pull request: <https://hub.docker.com/r/evoapicloud/evolution-go/tags>.
- The three upstream commits applied cleanly, in order, onto the exact 0.7.2 source revision during spec research. That proves backport compatibility at the Git level only; compilation, upstream tests, image build, license startup, and runtime behavior remain mandatory implementation acceptance work.
- PostgreSQL explicitly warns that `idle_session_timeout` can surprise pooling middleware. That is why it is restricted to Evolution's role and must pass the post-timeout messaging test before production: <https://www.postgresql.org/docs/15/runtime-config-client.html#GUC-IDLE-SESSION-TIMEOUT>.
- No existing ADR governs Evolution image selection or PostgreSQL pool limits, so this spec conflicts with no ADR. It explicitly supersedes the older v1 deployment decision only where that decision requires Evolution GO 0.7.1.
