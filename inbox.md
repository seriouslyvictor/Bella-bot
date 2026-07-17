# Bella-bot issue inbox

Use this file to capture newly observed issues before they are triaged into
the local issue tracker under `.scratch/<feature-slug>/issues/`.

## Conventions

- Add new issues at the top of the **Issues** section.
- Use an ISO 8601 timestamp with a timezone, for example
  `2026-07-16T18:30:00-03:00`.
- Set `Status` to one of the canonical triage labels: `needs-triage`,
  `needs-info`, `ready-for-agent`, `ready-for-human`, or `wontfix`.
- Until an issue is verified, use `Verified at: not verified` and
  `Verified by: not verified`.
- On verification, record both the verifier type (`human` or `agent`) and a
  name or identifier, for example `human: Bella` or `agent: Codex`.
- When an issue is moved to `.scratch/`, replace `Tracking issue: not created`
  with the new issue file's path.

## Issue template

Copy this block into the top of **Issues**:

```md
### Short issue title

- Reported at: YYYY-MM-DDTHH:MM:SS-03:00
- Status: needs-triage
- Verified at: not verified
- Verified by: not verified
- Tracking issue: not created

**Observed:**

What happened?

**Expected:**

What should have happened?

**Evidence:**

Logs, screenshots, message IDs, reproduction steps, or other useful context.
```

## Issues

<!-- Add new issues directly below this comment. -->

### Keep the course opening count up to date

- Reported at: 2026-07-16T22:38:33-03:00
- Status: needs-info
- Verified at: 2026-07-16T22:38:33-03:00
- Verified by: human: user
- Tracking issue: not created

**Observed:**

Bella always says that 19 openings remain for the course. This value is
hard-coded or stale and will become incorrect as enrollment changes.

**Expected:**

Bella should give the current number of openings obtained exclusively from
the following SENAI-SP source:

<https://www.sp.senai.br/cursos/cursos-livres/tecnologia-da-informacao-e-informatica?unidade=127>

On that page, find the course named **Inteligências Artificiais Generativas
Aplicada a Programação - ChatGPT**, follow its **VER TURMAS** action, and read
the current availability from the resulting class information. No other
source may be used for this value.

The retrieval may run periodically in the background with a freshness policy,
or in real time when Bella needs the value. The choice remains open pending a
latency, reliability, and freshness assessment. Bella must not fall back to
the stale value of 19 when the source cannot be read.

**Evidence:**

Reported and verified by the user. The SENAI-SP course listing exposes the
named course and a **VER TURMAS** action; the live opening count must be read
from the class details reached through that action.

**Discussion:**

- Choose between a scheduled background refresh, a real-time lookup, or a
  bounded-cache hybrid.
- Define the maximum acceptable age of a cached opening count.
- Define Bella's response when SENAI-SP is unavailable or its page structure
  changes.

### Show online presence and typing indication before replies

- Reported at: 2026-07-16T22:32:15-03:00
- Status: needs-triage
- Verified at: 2026-07-16T22:32:15-03:00
- Verified by: human: user
- Tracking issue: not created

**Observed:**

Bella does not appear online or show a "Typing..." indication while preparing
and sending a reply. The reply arrives without any visible activity, making
the interaction feel artificial.

**Expected:**

Bella should expose appropriate online presence and a typing indication while
preparing a response, then clear that state after sending the reply.

**Evidence:**

Reported and verified by the user during a live conversation with Bella.

### Define handling for message reactions

- Reported at: 2026-07-16T22:26:16-03:00
- Status: needs-info
- Verified at: 2026-07-16T22:26:16-03:00
- Verified by: human: user
- Tracking issue: not created

**Observed:**

When a user reacts to a message, Bella treats the reaction as a regular
message and replies that she does not understand it.

**Expected:**

Open for discussion. The current proposal is for reaction events to be
silently ignored, while ordinary messages containing emojis continue through
the normal message pipeline.

**Evidence:**

Reported and verified by the user, who clarified that this concerns message
reactions rather than ordinary emoji messages.

**Discussion:**

- Decide whether every reaction event should be ignored, regardless of which
  message was reacted to or which emoji was used.
