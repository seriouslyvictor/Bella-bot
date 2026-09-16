"""The per-message pipeline: safety checks, Scope Gate, then a guarded reply.

This module owns the invariants that must hold from day one: never reply to
our own echoed messages (from-me messages are classified, not blanket-
dropped — see EchoLedger), never reply twice to the same delivery, always
send the user a reply, and never let a processing error escape after the
webhook has already been acknowledged.

Every reply to a user — canned, model-authored, or feedback-dialogue —
leaves through `_reply_with_presence`, which hands it to the ResponsePolicy
(see `bella.response`). That is the single funnel where the URL allowlist, the
WhatsApp formatting rules, the non-empty guarantee, and message splitting are
applied; a user-facing branch that sends text any other way is a bug. The two
non-user sends — the Control Channel's command acknowledgements and the
handoff notification to the admin — are fixed operator-facing strings and go
out as written.

The always-reply invariant has exactly one sanctioned exception: a
Takeover Pause (ADR 0003). While the course owner has typed into a
conversation, Bella stores the user's messages but sends nothing, because
the human owns the reply obligation. Do not "fix" that silence.
"""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any, Protocol

from bella.answer_guard import find_urls
from bella.canned_replies import CannedReplies
from bella.control_channel import (
    DiagCommand,
    VoltarCommand,
    not_paused_reply,
    parse_command,
    resumed_reply,
)
from bella.conversation_store import (
    ConversationMessage,
    ConversationStore,
)
from bella.evolution import InboundMessage, PresenceState, WhatsAppSender
from bella.feedback_collector import FeedbackCollector, FeedbackPhase
from bella.rate_limit import (
    RateLimitDecision,
    RateLimitPolicy,
    SlidingWindowRateLimiter,
)
from bella.reply_language import ReplyLanguage, detect_reply_language
from bella.response import (
    Response,
    ResponsePolicy,
    ResponseSource,
    policy_from_urls,
)
from bella.retention import run_retention_job
from bella.scope_gate import RouteCategory, ScopeGate
from bella.triage_worker import TriageWorker

if TYPE_CHECKING:
    # diagnostics imports Answerer from this module, so the seam is typed
    # without making the import cycle real at runtime.
    from bella.diagnostics import SelfTest

logger = logging.getLogger("bella")


class RefusalRotation:
    """Bounded per-recipient refusal rotation (Postgres in ticket 06).

    Out-of-scope traffic is the unbounded, adversarial surface — spam, wrong
    numbers, injection probes — so the recipient keys are attacker-chosen and
    must not accumulate forever. Evicting a cold recipient only costs them a
    restart of the rotation, which is invisible.
    """

    def __init__(self, refusals: Sequence[str], capacity: int = 2048) -> None:
        self._refusals = tuple(refusals)
        self._next: OrderedDict[str, int] = OrderedDict()
        self._capacity = capacity

    def take(self, recipient: str) -> str:
        index = self._next.get(recipient, 0)
        self._next[recipient] = index + 1
        self._next.move_to_end(recipient)
        if len(self._next) > self._capacity:
            self._next.popitem(last=False)
        return self._refusals[index % len(self._refusals)]


class EchoLedger:
    """Bounded in-process record of Bella's own outgoing sends.

    Distinguishes Bella's own from-me webhook echoes from a human typing
    into the same chat (ADR 0003, consequence 1). The expected outgoing
    (recipient, text) is registered *before* the send call, and the
    provider message ID is filled in once the call returns. The
    (recipient, text) registration stays live until an inbound echo
    actually consumes it — matching by id is just the fast path; an echo
    that beats the send response still matches by (recipient, text).

    Not persisted, and bounded like RefusalRotation above: a miss after
    eviction or a restart mis-reads one echo as human and pauses one
    conversation for one window — a bounded, invisible failure accepted
    by design.
    """

    def __init__(self, capacity: int = 2048) -> None:
        self._capacity = capacity
        self._pending: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._ids: OrderedDict[str, tuple[str, str]] = OrderedDict()

    def register(self, recipient: str, text: str) -> tuple[str, str]:
        key = (recipient, text)
        self._pending[key] = self._pending.get(key, 0) + 1
        self._pending.move_to_end(key)
        while len(self._pending) > self._capacity:
            self._pending.popitem(last=False)
        return key

    def cancel(self, key: tuple[str, str]) -> None:
        """Release a registration whose send call failed before returning an id."""
        self._release_pending(key)

    def record_id(self, key: tuple[str, str], message_id: str) -> None:
        self._ids[message_id] = key
        self._ids.move_to_end(message_id)
        while len(self._ids) > self._capacity:
            self._ids.popitem(last=False)

    def is_own_echo(self, message_id: str, recipient: str, text: str | None) -> bool:
        key = self._ids.pop(message_id, None)
        if key is not None:
            self._release_pending(key)
            return True
        if text is None:
            return False
        return self._release_pending((recipient, text))

    def _release_pending(self, key: tuple[str, str]) -> bool:
        count = self._pending.get(key, 0)
        if count <= 0:
            return False
        if count == 1:
            del self._pending[key]
        else:
            self._pending[key] = count - 1
        return True


def _current_time() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AnswerResult:
    text: str
    needs_handoff: bool = False


class Answerer(Protocol):
    async def answer(
        self,
        text: str,
        category: RouteCategory,
        history: Sequence[ConversationMessage],
    ) -> AnswerResult: ...


class Pipeline:
    def __init__(
        self,
        sender: WhatsAppSender,
        scope_gate: ScopeGate,
        answerer: Answerer,
        canned_replies: CannedReplies,
        enrollment_url: str,
        conversation_store: ConversationStore,
        apostila_path: Path,
        human_contact_reply: str,
        admin_contact: str,
        rate_limit_policy: RateLimitPolicy,
        rate_limit_clock: Callable[[], float] = monotonic,
        takeover_pause_seconds: int = 3600,
        takeover_clock: Callable[[], datetime] = _current_time,
        feedback_collector: FeedbackCollector | None = None,
        support_answerer: Answerer | None = None,
        triage_worker: TriageWorker | None = None,
        response_policy: ResponsePolicy | None = None,
        reply_timeout_seconds: float = 30.0,
        self_test: "SelfTest | None" = None,
        failure_notice_interval_seconds: float = 300.0,
    ) -> None:
        self._sender = sender
        self._scope_gate = scope_gate
        self._answerer = answerer
        self._canned_replies = canned_replies
        # Kept as the seed of the reply URL allowlist below; no branch reads
        # it directly any more (the guard moved into the ResponsePolicy).
        self._enrollment_url = enrollment_url
        self._conversation_store = conversation_store
        self._apostila_path = apostila_path
        self._human_contact_reply = human_contact_reply
        self._admin_contact = "".join(
            character for character in admin_contact if character.isdigit()
        )
        # One rotation per language: a refusal is the only reply an
        # out-of-scope user ever gets, and it is produced without a model, so
        # the localized wording has to be chosen here.
        self._refusals = {
            language: RefusalRotation(canned_replies.refusals_for(language))
            for language in ReplyLanguage
        }
        self._response_policy = response_policy or policy_from_urls(
            canned_replies.error_reply,
            # Our own handoff block is trusted text; its links stay allowed so
            # the guard cannot delete the contact it is meant to deliver.
            (enrollment_url, *find_urls(human_contact_reply)),
            translations={
                language.value: canned_replies.reply("error_reply", language)
                for language in ReplyLanguage
            },
        )
        self._reply_timeout_seconds = reply_timeout_seconds
        self._self_test = self_test
        # A broken dependency fails every message, so the admin gets the
        # real exception at most once per window instead of once per user.
        self._failure_notice_interval = failure_notice_interval_seconds
        self._last_failure_notice: float | None = None
        self._rate_limiter = SlidingWindowRateLimiter(
            rate_limit_policy,
            rate_limit_clock,
        )
        self._echo_ledger = EchoLedger()
        self._presence_tasks: set[asyncio.Task[None]] = set()
        self._presence_tails: dict[str, asyncio.Task[None]] = {}
        self._active_reply_counts: dict[str, int] = {}
        self._takeover_pause_window = timedelta(seconds=takeover_pause_seconds)
        self._clock = takeover_clock
        self._feedback_collector = feedback_collector
        self._support_answerer = support_answerer or answerer
        self._triage_worker = triage_worker
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def start(self) -> None:
        await self._conversation_store.start()

    async def close(self) -> None:
        if self._presence_tasks:
            await asyncio.gather(
                *tuple(self._presence_tasks),
                return_exceptions=True,
            )
        if self._background_tasks:
            await asyncio.gather(
                *tuple(self._background_tasks),
                return_exceptions=True,
            )
        await self._conversation_store.close()

    async def check_readiness(self) -> None:
        # Both local dependencies are required to accept a webhook: Postgres
        # claims the delivery first, then Evolution sends the reply. Probe in
        # parallel and cap the whole check below Docker's five-second timeout.
        async with asyncio.timeout(4):
            await asyncio.gather(
                self._conversation_store.check_health(),
                self._sender.check_health(),
            )

    async def run_retention(self) -> None:
        await run_retention_job(self._conversation_store)

    async def handle(self, message: InboundMessage) -> None:
        """Process one inbound message. Never raises — the ack already went out."""
        try:
            await self._handle(message)
        except Exception:
            logger.exception("failed to process message %s", message.message_id)

    async def _handle(self, message: InboundMessage) -> None:
        if message.is_group:
            # Bella never speaks in groups (Bella v1 spec story 24), from-me
            # or not. Full input policy lands in ticket 09, but this guard
            # must precede deployment.
            return
        if not await self._conversation_store.claim_delivery(message.message_id):
            logger.info("duplicate delivery ignored: %s", message.message_id)
            return
        if message.is_from_me:
            await self._handle_takeover_signal(message)
            return
        if (
            self._admin_contact
            and message.number == self._admin_contact
            and await self._handle_control_channel(message)
        ):
            return
        if await self._pause_active(message.number):
            # The human owns this conversation's reply obligation (ADR 0003):
            # store the message for context, but no Scope Gate, no LLM, no canned
            # reply, no rate-limit notice. Checked before the rate limiter so
            # a pause-era message never feeds its accounting.
            await self._conversation_store.append_message(
                message.number,
                ConversationMessage(
                    "user", self._memory_text(message), datetime.now(UTC)
                ),
            )
            logger.info(
                "takeover pause active, no reply sent: %s", message.message_id
            )
            return
        rate_limit = self._rate_limiter.check(message.number)
        if rate_limit is RateLimitDecision.SILENCE:
            logger.info("rate-limited message silenced: %s", message.message_id)
            return
        language = detect_reply_language(message.text)
        if rate_limit is RateLimitDecision.NOTIFY:
            await self._reply_with_presence(
                message.number, self._canned_plan("rate_limit_reply", language)
            )
            logger.info("rate-limit notice sent: %s", message.message_id)
            return
        text = message.text
        if text is None:
            logger.info(
                "non-text message receives canned reply: %s (type=%s)",
                message.message_id,
                message.message_type,
            )
            await self._reply_with_presence(
                message.number, self._canned_plan("media_reply", language)
            )
            return

        plan = await self._reply_with_presence(
            message.number,
            self._produce_reply(text, message.number, language, message.message_id),
        )
        await self._conversation_store.append_message(
            message.number,
            ConversationMessage("assistant", plan.text, datetime.now(UTC)),
        )
        if plan.needs_handoff:
            await self._notify_admin(message.number, text)
        logger.info("replied to %s (message %s)", message.number, message.message_id)

    async def _canned_plan(self, key: str, language: ReplyLanguage) -> Response:
        return Response(
            self._canned_replies.reply(key, language),
            ResponseSource.CANNED,
            language,
        )

    async def _produce_reply(
        self,
        text: str,
        number: str,
        language: ReplyLanguage,
        message_id: str,
    ) -> Response:
        history = await self._conversation_store.recent_messages(number)
        await self._conversation_store.append_message(
            number,
            ConversationMessage("user", text, datetime.now(UTC)),
        )
        try:
            # The webhook was acked long before this runs, so a provider that
            # never answers would otherwise mean a user who never hears back.
            # The deadline turns a hung call into the canned error reply.
            async with asyncio.timeout(self._reply_timeout_seconds):
                return await self._reply_for(text, number, history, language)
        except Exception as error:
            # Guards the whole reply-producing step, not just one stage of it:
            # every stage added here must degrade to a reply, never to silence.
            logger.exception("reply production failed for %s", message_id)
            # The user gets the canned apology; the operator gets the cause.
            # Without this, an outage is indistinguishable from a bad answer
            # unless someone is watching the container logs.
            await self._notify_admin_failure(number, error)
            return Response(
                self._canned_replies.reply("error_reply", language),
                ResponseSource.CANNED,
                language,
            )

    async def _handle_takeover_signal(self, message: InboundMessage) -> None:
        """A from-me message is either Bella's own echo or a human typing in.

        A genuine Takeover message sets/extends the pause; text is also
        recorded under the Owner role so Bella has context after resume
        without ever inheriting a human commitment as her own (ticket 03).
        Media messages (text is None) only re-arm the pause.
        """
        if self._echo_ledger.is_own_echo(
            message.message_id,
            message.number,
            message.text or message.media_caption,
        ):
            return
        until = self._clock() + self._takeover_pause_window
        await self._conversation_store.set_pause(message.number, until)
        if message.text is not None:
            await self._conversation_store.append_message(
                message.number,
                ConversationMessage("owner", message.text, datetime.now(UTC)),
            )
        logger.info(
            "takeover pause set for %s (%d min, until %s)",
            message.number,
            int(self._takeover_pause_window.total_seconds() // 60),
            until.isoformat(timespec="minutes"),
        )

    async def _handle_control_channel(self, message: InboundMessage) -> bool:
        """Admin-number commands are parsed deterministically, before the
        Scope Gate/LLM (spec story 11) — and before the pause check, so
        `voltar` still works even though the admin's own chat could itself
        be paused (spec story 8; harmless per ADR 0003). Returns False for
        unrecognized text so the caller falls through to the normal
        pipeline (spec story 12). A command is control traffic, not
        conversation: it is never appended to history or fed to the rate
        limiter, but delivery was already deduped by claim_delivery above,
        so a redelivered `voltar` is not double-confirmed.
        """
        if message.text is None:
            return False
        command = parse_command(message.text)
        if command is None:
            return False
        if isinstance(command, DiagCommand):
            await self._send_text(message.number, await self._run_self_test())
            logger.info(
                "control channel diag handled (message %s)", message.message_id
            )
            return True
        assert isinstance(command, VoltarCommand)
        if await self._pause_active(command.target_number):
            await self._conversation_store.clear_pause(command.target_number)
            reply = resumed_reply(command.target_number)
        else:
            reply = not_paused_reply(command.target_number)
        # The admin's own chat is the reply target: parse_command is pure
        # text-to-command and carries no source/transport knowledge.
        await self._send_text(message.number, reply)
        logger.info(
            "control channel voltar handled for %s (message %s)",
            command.target_number,
            message.message_id,
        )
        return True

    async def _pause_active(self, phone_number: str) -> bool:
        until = await self._conversation_store.paused_until(phone_number)
        return until is not None and until > self._clock()

    @staticmethod
    def _memory_text(message: InboundMessage) -> str:
        if message.text is not None:
            return message.text
        media_type = message.message_type.strip() or "desconhecida"
        marker = f"[Mídia recebida: {media_type}]"
        if message.media_caption is not None:
            return f"{marker} {message.media_caption}"
        return marker

    async def _reply_with_presence(
        self, number: str, produce: Awaitable[Response]
    ) -> Response:
        """Bracket presence around producing, finalizing and sending a reply.

        Composing must cover the seconds of reply production, not just the
        send. This is also the single funnel every user-facing reply passes
        through, so the ResponsePolicy runs here: whatever a branch produced,
        what leaves is guarded, WhatsApp-formatted, non-empty and split into
        sendable messages. The returned Response carries the finalized text so
        conversation history records what the user actually saw. The apostila
        path already sent its own document, so an already_sent response skips
        the send but still clears presence.
        """
        async with self._reply_presence(number):
            response = await produce
            chunks = self._response_policy.finalize(response)
            if not response.already_sent:
                for chunk in chunks:
                    await self._send_text(number, chunk)
            return replace(response, text="\n\n".join(chunks))

    @asynccontextmanager
    async def _reply_presence(self, number: str) -> AsyncIterator[None]:
        # Only touched from the asyncio event loop with no await between
        # reading and writing the counter, so plain dict operations are
        # race-free — no lock needed.
        active_count = self._active_reply_counts.get(number, 0)
        self._active_reply_counts[number] = active_count + 1
        try:
            if active_count == 0:
                await self._signal_presence(number, "available")
                await self._signal_presence(number, "composing")
            yield
        finally:
            remaining = self._active_reply_counts[number] - 1
            if remaining:
                self._active_reply_counts[number] = remaining
            else:
                self._active_reply_counts.pop(number)
            if remaining == 0:
                await self._signal_presence(number, "paused")

    async def _signal_presence(
        self, number: str, state: PresenceState
    ) -> None:
        previous = self._presence_tails.get(number)
        task = asyncio.create_task(
            self._send_presence_after(previous, number, state)
        )
        self._presence_tasks.add(task)
        self._presence_tails[number] = task
        task.add_done_callback(
            lambda completed: self._presence_finished(
                completed,
                number,
                state,
            )
        )
        # Give the request coroutine a chance to start, but never wait for
        # provider latency: presence is strictly best-effort.
        await asyncio.sleep(0)

    async def _send_presence_after(
        self,
        previous: asyncio.Task[None] | None,
        number: str,
        state: PresenceState,
    ) -> None:
        if previous is not None:
            # Preserve provider application order even when an earlier request
            # is slow or fails. Waiting happens only inside the fire-and-forget
            # chain, so it cannot delay the actual reply.
            await asyncio.gather(previous, return_exceptions=True)
        await self._sender.send_presence(number, state)

    def _presence_finished(
        self,
        task: asyncio.Task[None],
        number: str,
        state: PresenceState,
    ) -> None:
        self._presence_tasks.discard(task)
        if self._presence_tails.get(number) is task:
            self._presence_tails.pop(number, None)
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception as error:
            logger.warning(
                "presence signal failed for %s state=%s (%s)",
                number,
                state,
                type(error).__name__,
            )

    async def _send_text(self, number: str, text: str) -> None:
        """Every send to a user chat is registered before the call so a
        webhook echo that beats the send response still matches by
        (recipient, text) (ADR 0003, consequence 1)."""
        key = self._echo_ledger.register(number, text)
        try:
            message_id = await self._sender.send_text(number, text)
        except Exception:
            self._echo_ledger.cancel(key)
            raise
        if message_id:
            self._echo_ledger.record_id(key, message_id)

    async def _send_document(self, number: str, path: Path, caption: str) -> None:
        """Register the caption before sending so an early document echo can
        match even before its provider ID is known (ADR 0003, consequence 1)."""
        key = self._echo_ledger.register(number, caption)
        try:
            message_id = await self._sender.send_document(number, path, caption)
        except Exception:
            self._echo_ledger.cancel(key)
            raise
        if message_id:
            self._echo_ledger.record_id(key, message_id)

    async def _run_self_test(self) -> str:
        """Answer `diag` with what each dependency actually did."""
        if self._self_test is None:
            return "Diagnóstico indisponível: self-test não configurado."
        from bella.diagnostics import describe_error, format_report

        try:
            return format_report(await self._self_test.run())
        except Exception as error:
            logger.exception("self-test failed")
            return f"Diagnóstico falhou: {describe_error(error)}"

    async def _notify_admin_failure(
        self, user_number: str, error: BaseException
    ) -> None:
        """Forward a reply-production failure to the admin, at most once per
        window. A dependency outage fails every inbound message, so an
        unthrottled notice would bury the admin in the same error."""
        if not self._admin_contact or user_number == self._admin_contact:
            return
        now = monotonic()
        if (
            self._last_failure_notice is not None
            and now - self._last_failure_notice < self._failure_notice_interval
        ):
            return
        self._last_failure_notice = now
        from bella.diagnostics import describe_error

        notification = (
            "Falha da Nova\n"
            f"Usuario: {user_number}\n"
            f"Erro: {describe_error(error)}\n"
            "Envie 'diag' para testar cada dependência."
        )
        try:
            await self._send_text(self._admin_contact, notification)
        except Exception:
            logger.exception("failed to notify admin about a reply failure")

    async def _notify_admin(self, user_number: str, summary: str) -> None:
        if not self._admin_contact or user_number == self._admin_contact:
            return
        notification = (
            "Handoff Bella\n"
            f"Usuario: {user_number}\n"
            f"Pedido: {summary[:500]}"
        )
        try:
            await self._send_text(self._admin_contact, notification)
        except Exception:
            logger.exception("failed to notify admin about %s", user_number)

    async def _reply_for(
        self,
        text: str,
        number: str,
        history: Sequence[ConversationMessage],
        language: ReplyLanguage,
    ) -> Response:
        # 1. If user is in an active feedback session (phase is not IDLE)
        if self._feedback_collector is not None:
            phase, _ = await self._conversation_store.get_feedback_draft(number)
            if phase != FeedbackPhase.IDLE:
                return await self._feedback_turn(number, text, history, language)

        # 2. If not in feedback session, classify with scope_gate.classify(text)
        category = await self._scope_gate.classify(text)
        if category is RouteCategory.OUT_OF_SCOPE:
            return self._canned(self._refusal_for(number, language), language)
        if category is RouteCategory.GREETING:
            greeting = self._canned_replies.reply("greeting_reply", language)
            if not greeting:
                greeting = self._refusal_for(number, language)
            return self._canned(greeting, language)
        if category is RouteCategory.HUMAN_REQUESTED:
            return self._handoff_response(language)
        if category is RouteCategory.APP_FEEDBACK:
            if self._feedback_collector is not None:
                return await self._feedback_turn(number, text, history, language)
        if category is RouteCategory.APOSTILA_REQUEST:
            if not self._apostila_path.is_file():
                return self._canned(
                    self._canned_replies.reply("apostila_soon_reply", language),
                    language,
                )
            caption = self._canned_replies.reply("apostila_caption", language)
            try:
                await self._send_document(
                    number,
                    self._apostila_path,
                    caption,
                )
            except Exception:
                logger.exception("failed to send apostila to %s", number)
                return self._canned(
                    self._canned_replies.reply("apostila_error_reply", language),
                    language,
                )
            return Response(
                caption,
                ResponseSource.CANNED,
                language,
                already_sent=True,
            )

        target_answerer = self._support_answerer or self._answerer
        answer = await target_answerer.answer(text, category, history)
        reply_text = answer.text
        if answer.needs_handoff and self._human_contact_reply:
            # Only attach the heading when there is a contact under it; an
            # unconfigured deployment used to emit a dangling "Contato humano:".
            heading = self._canned_replies.reply("human_contact_intro", language)
            reply_text = (
                f"{reply_text}\n\n{heading}\n{self._human_contact_reply}"
            )
        # The URL allowlist is applied by the ResponsePolicy, which knows this
        # text is model-authored — see `_reply_with_presence`.
        return Response(
            reply_text,
            ResponseSource.ANSWERER,
            language,
            needs_handoff=answer.needs_handoff,
        )

    def _canned(self, text: str, language: ReplyLanguage) -> Response:
        return Response(text, ResponseSource.CANNED, language)

    def _refusal_for(self, number: str, language: ReplyLanguage) -> str:
        return self._refusals[language].take(number)

    def _handoff_response(self, language: ReplyLanguage) -> Response:
        """Hand the user a person to talk to, or say a person was notified.

        The admin notification fires either way (`needs_handoff`), so a
        deployment with no configured contact still reaches a human — what it
        must not do is answer the user with an empty message.
        """
        if not self._human_contact_reply:
            return Response(
                self._canned_replies.reply("no_contact_reply", language),
                ResponseSource.CANNED,
                language,
                needs_handoff=True,
            )
        contact = self._human_contact_reply
        if language is not ReplyLanguage.PORTUGUESE:
            intro = self._canned_replies.reply("human_contact_intro", language)
            contact = f"{intro}\n{contact}"
        return Response(
            contact,
            ResponseSource.CANNED,
            language,
            needs_handoff=True,
        )

    async def _feedback_turn(
        self,
        number: str,
        text: str,
        history: Sequence[ConversationMessage],
        language: ReplyLanguage,
    ) -> Response:
        """One turn of the feedback dialogue, including the triage kick-off.

        The collector's reply is partly model-authored (the follow-up
        question), so it is tagged FEEDBACK and gets the same output guard as
        any other generated text.
        """
        assert self._feedback_collector is not None
        result = await self._feedback_collector.process_turn(
            number, text, self._conversation_store, history
        )
        if result.confirmed and self._triage_worker is not None:
            task = asyncio.create_task(self._triage_worker.process_pending())
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        return Response(result.reply_text, ResponseSource.FEEDBACK, language)
