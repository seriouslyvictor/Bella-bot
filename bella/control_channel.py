"""Control Channel command parsing (spec story 23, ADR 0003).

Source-agnostic: this module knows nothing about Evolution, webhooks, or the
admin contact number. It only turns command text into a parsed command, so a
second Control Channel source (the self-chat, out of scope for this ticket)
can reuse `parse_command` unchanged. The caller decides where the command
came from and where the reply goes.

Commands are matched by a plain regex, never routed through an LLM (spec
story 11) — takeover control cannot be misclassified or prompt-injected.
"""

import re
from dataclasses import dataclass

_VOLTAR_PATTERN = re.compile(r"^voltar\s+(.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class VoltarCommand:
    target_number: str  # digits-only, matches a ConversationStore key


def parse_command(text: str) -> VoltarCommand | None:
    """Parse one line of admin command text.

    Number matching is digits-only and tolerant of formatting (punctuation,
    spaces, country-code spacing) so the owner can paste straight from a
    Handoff Notification. Anything unrecognized returns None so the caller
    falls through to the normal pipeline (spec story 12). Matching is exact
    on digits, so a manually typed number that differs from the stored key
    (e.g. a missing country code) safely yields the honest not-paused notice
    rather than resuming a wrong chat.
    """
    match = _VOLTAR_PATTERN.match(text.strip())
    if match is None:
        return None
    target_number = "".join(
        character for character in match.group(1) if character.isdigit()
    )
    if not target_number:
        return None
    return VoltarCommand(target_number)


def resumed_reply(target_number: str) -> str:
    return f"Bella reativada para {target_number}."


def not_paused_reply(target_number: str) -> str:
    return f"Nenhuma pausa ativa para {target_number}."
