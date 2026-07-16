# 01 — Build the patched Evolution GO 0.7.2 runtime

**What to build:** A reproducible Bella-owned Evolution GO runtime that keeps the working 0.7.2 behavior while incorporating only upstream pull request #117's connection-pool fix. The unified stack must build and identify this runtime explicitly instead of pulling `latest`, and operators must be able to prove which upstream source, patch, and image artifact are deployed.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] The runtime is based only on upstream Evolution GO 0.7.2 source commit `9337afc47e10b86cc896a6f432240e40fee95dd1`
- [ ] The reviewed commits `4cc635dd460f70c36ba83285ecbb34589790572f`, `f85ea1445373ea142bb12ba0c01dfc85879be212`, and `03289559d547911d92ad58837db98faeb0c5fd8e` are applied in order, and the build fails if they do not apply exactly
- [ ] The patch is retained as a reviewed repository build input, so production does not depend on a mutable pull-request branch
- [ ] Build-stage and runtime base images are pinned by digest, and fetched upstream source is pinned and checksum-verified
- [ ] The resulting image has the non-floating identity `bella/evolution-go:0.7.2-pr117-0328955` and exposes source and patch provenance in operator-visible metadata
- [ ] The unified stack builds and runs this image without changing its three-service topology, internal addresses, persistent storage, or production port exposure
- [ ] No `latest`, `develop`, or unpinned Evolution image remains in the deployment contract
- [ ] The backport preserves one shared authentication-store container, at most 20 open and 5 idle PostgreSQL connections, five-minute connection lifetime, two-minute idle lifetime, and retry after failed initialization
- [ ] The upstream regression test proves failed initialization is not cached and successful calls reuse the same container
- [ ] The custom image starts successfully and its health, Manager, licensing, API, and webhook surfaces remain compatible with the current 0.7.2 deployment
- [ ] Deployment contract tests reject floating image regressions and pass with the patched runtime
- [ ] A clean-cache build succeeds for the production architecture and records the resulting image digest as deployment evidence
