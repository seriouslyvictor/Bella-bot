"""A self-test the owner can run from WhatsApp instead of reading logs.

Every failure inside reply production degrades to one canned error reply
(`bella.pipeline`), which is right for the user and useless for the operator:
a broken model name, an unreachable database and a rejected request all look
identical from the chat. When the logs are not at hand — a hosted deploy, a
phone, someone else's machine — there is otherwise no way to tell which leg
is down.

This module exercises each leg independently with a fixed probe and reports
what each one did, so "the bot is broken" becomes "the agent model is
rejecting the request and here is its error".

Probes are read-only and cheap: two health checks and, at most, three small
model calls. Nothing is written to a conversation, and nothing here is ever
reachable by a user — the Control Channel only accepts it from the admin
contact.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from bella.conversation_store import ConversationStore
from bella.evolution import WhatsAppSender
from bella.feedback_collector import FeedbackCollector
from bella.pipeline import Answerer
from bella.scope_gate import RouteCategory, ScopeGate

logger = logging.getLogger("bella")

# Deliberately mundane: an in-scope support question that any working
# configuration answers, so a failure is the configuration and not the probe.
PROBE_TEXT = "como faço para gerar um relatório?"
PROBE_TIMEOUT_SECONDS = 20.0
DETAIL_LIMIT = 160


@dataclass(frozen=True)
class ProbeResult:
    name: str
    ok: bool
    detail: str


def describe_error(error: BaseException) -> str:
    """The exception class plus its message — the two things a log would give."""
    message = str(error).strip().replace("\n", " ")
    if not message:
        return type(error).__name__
    return f"{type(error).__name__}: {message}"[:DETAIL_LIMIT]


async def _probe(name: str, run: Callable[[], Awaitable[str]]) -> ProbeResult:
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            detail = await run()
    except Exception as error:  # noqa: BLE001 — reporting is the whole point
        logger.warning("self-test probe %s failed: %s", name, describe_error(error))
        return ProbeResult(name, False, describe_error(error))
    return ProbeResult(name, True, detail[:DETAIL_LIMIT])


class SelfTest:
    """Runs one probe per external dependency the reply path depends on."""

    def __init__(
        self,
        conversation_store: ConversationStore,
        sender: WhatsAppSender,
        scope_gate: ScopeGate,
        answerer: Answerer,
        feedback_collector: FeedbackCollector | None = None,
    ) -> None:
        self._conversation_store = conversation_store
        self._sender = sender
        self._scope_gate = scope_gate
        self._answerer = answerer
        self._feedback_collector = feedback_collector

    async def run(self) -> tuple[ProbeResult, ...]:
        async def postgres() -> str:
            await self._conversation_store.check_health()
            return "ok"

        async def whatsapp() -> str:
            await self._sender.check_health()
            return "ok"

        async def router() -> str:
            category = await self._scope_gate.classify(PROBE_TEXT)
            return f"classificou como {category.value}"

        async def agent() -> str:
            answer = await self._answerer.answer(
                PROBE_TEXT, RouteCategory.APP_SUPPORT, ()
            )
            return f"respondeu {len(answer.text)} caracteres"

        probes: list[tuple[str, Callable[[], Awaitable[str]]]] = [
            ("banco de dados", postgres),
            ("whatsapp", whatsapp),
            ("modelo roteador", router),
            ("modelo agente", agent),
        ]
        collector = self._feedback_collector
        if collector is not None:

            async def extractor() -> str:
                extracted = await collector.extract_draft(PROBE_TEXT)
                return f"extraiu {extracted.title[:60]!r}"

            probes.append(("extrator de feedback", extractor))

        return tuple(
            await asyncio.gather(*(_probe(name, run) for name, run in probes))
        )


def format_report(results: Sequence[ProbeResult]) -> str:
    """One WhatsApp message the owner can read at a glance."""
    lines = ["*Diagnóstico da Nova*", ""]
    for result in results:
        mark = "✅" if result.ok else "❌"
        lines.append(f"{mark} *{result.name}*: {result.detail}")
    broken = [result.name for result in results if not result.ok]
    lines.append("")
    if broken:
        lines.append(f"Falhando: {', '.join(broken)}.")
    else:
        lines.append("Tudo respondendo normalmente.")
    return "\n".join(lines)
