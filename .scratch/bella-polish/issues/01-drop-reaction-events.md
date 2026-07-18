# 01 — Drop reaction events at the normalization point

**What to build:** A WhatsApp user who reacts to one of Bella's messages (or
removes a reaction) gets exactly nothing back — no canned "I don't
understand" reply, no entry in conversation history, no visible activity.
The course owner reacting to a user's message from Bella's own number no
longer arms a Takeover Pause: a reaction is an annotation, not Takeover
typing (consistent with ADR 0003). Ordinary messages that merely contain
emoji — even emoji-only messages — still flow through the Scope Gate
pipeline and get answered normally.

Reaction deliveries are recognized and dropped at the Evolution GO
wire-normalization point, before a pipeline message exists, so they produce
no delivery claim, no presence, and no reply on any path. Each drop is
logged so traffic stays observable.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] A simulated reaction delivery through the webhook is acked with no
      outbound sends and no conversation-history entry.
- [x] A reaction-removal delivery behaves identically.
- [x] A from-me reaction does not arm or extend a Takeover Pause: a user
      message following it still gets a normal reply.
- [x] An emoji-only text message still receives a normal pipeline reply.
- [x] Dropped reaction events appear in the logs.
