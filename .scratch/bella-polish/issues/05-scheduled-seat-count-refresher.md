# 05 — Scheduled seat-count refresher with freshness policy

**What to build:** The tracer connects end-to-end: a prospective student who
asks about openings gets the real, current SENAI-SP count — instantly, from
cache, with no page-load latency in the conversation. A background job
(following the existing lifespan background-job pattern) invokes the
availability source on a fixed interval and stores the parsed count with a
fetched-at timestamp in the shared holder that the Enrollment Card
rendering already reads.

Freshness policy: refresh interval defaulting to 6 hours and maximum
acceptable age defaulting to 24 hours, both overridable through the
environment. A failed refresh keeps the last good value until it exceeds
the maximum age; after that the seats fact is omitted and Bella deflects
honestly. A transient SENAI-SP outage inside the maximum age is invisible
to users.

**Blocked by:** 03 — Seats fact rendered from a live holder; 04 — SENAI-SP
availability source.

**Status:** ready-for-agent

- [x] The refresher runs at application lifespan on the configured interval
      and feeds the holder on each successful fetch.
- [x] After a successful refresh, Bella's rendered Enrollment Card carries
      the fetched count.
- [x] A failed refresh inside the maximum age keeps the last good count.
- [x] Beyond the maximum age the seats fact is omitted (honest deflection),
      driven by a fake clock in tests.
- [x] Refresh interval and maximum age are environment-tunable, with the
      6-hour/24-hour defaults.
- [x] Every failed refresh logs a warning with the reason.
