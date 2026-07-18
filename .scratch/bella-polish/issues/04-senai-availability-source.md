# 04 — SENAI-SP availability source

**What to build:** The one new seam of this spec: an availability-source
abstraction that owns the entire interaction with SENAI-SP at the HTTP
boundary — fetching the designated course-listing page, locating the course
"Inteligências Artificiais Generativas Aplicada a Programação - ChatGPT",
following its VER TURMAS action to the class details, and parsing the
current opening count out of them. No other source may feed the count.

The SENAI-SP course-listing URL that seeds the fetch becomes a new field of
the editable Enrollment Card file, next to the enrollment URL it already
owns. Every anomaly — unreachable page, missing course row, missing VER
TURMAS target, unparseable availability — is one and the same failure mode:
a failed fetch with a warning logged stating the reason. A page-structure
change must degrade to a failure, never to a wrong number.

Standalone verifiability: an operator script (following the repo's existing
operator-script pattern) invokes the source against the live site and
prints the current count, so the seam can be proven end-to-end before the
refresher exists.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] The availability source returns the current opening count from
      captured fixture payloads of the real SENAI-SP pages.
- [x] Each anomaly (unreachable page, course row missing, VER TURMAS target
      missing, unparseable availability) yields a failed fetch and a warning
      log with the reason — never a number.
- [x] The course-listing URL is read from the Enrollment Card file.
- [x] The operator script prints the live count against the real site.
- [x] Page parsing lives entirely behind the seam; nothing outside it knows
      the page structure.
