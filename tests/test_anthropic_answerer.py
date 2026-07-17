"""Unit tests for the API message-framing translation.

AnthropicAnswerer talks to the real Anthropic API and isn't exercised through
the webhook seam (webhook tests use FakeAnswerer). `_build_messages` is the
pure, extracted piece of that translation — in particular the <owner_message>
framing (ticket 03) that keeps a human commitment made during a takeover from
being replayed as one of Bella's own — so it's unit-tested directly here.
"""

from datetime import UTC, datetime

from bella.anthropic_answerer import _build_messages
from bella.conversation_store import ConversationMessage
from bella.scope_gate import RouteCategory


def test_owner_history_is_reframed_as_a_user_turn_with_an_explicit_marker() -> None:
    history = [
        ConversationMessage(
            "owner", "vou te dar 10% de desconto", datetime.now(UTC)
        ),
    ]

    messages = _build_messages("oi", RouteCategory.COURSE_QUESTION, history)

    assert messages[0] == {
        "role": "user",
        "content": "<owner_message>\nvou te dar 10% de desconto\n</owner_message>",
    }


def test_user_and_assistant_history_pass_through_role_and_text_unchanged() -> None:
    history = [
        ConversationMessage("user", "oi", datetime.now(UTC)),
        ConversationMessage("assistant", "ola!", datetime.now(UTC)),
    ]

    messages = _build_messages("de novo", RouteCategory.COURSE_QUESTION, history)

    assert messages[0] == {"role": "user", "content": "oi"}
    assert messages[1] == {"role": "assistant", "content": "ola!"}


def test_current_turn_is_appended_last_with_category_and_user_message_tag() -> None:
    messages = _build_messages("qual o preco?", RouteCategory.COURSE_QUESTION, [])

    assert messages[-1] == {
        "role": "user",
        "content": (
            "Scope Gate category: course_question\n"
            "<user_message>\nqual o preco?\n</user_message>"
        ),
    }


def test_owner_and_ordinary_turns_are_distinguishable_in_the_built_messages() -> None:
    history = [
        ConversationMessage("owner", "eu assumo daqui", datetime.now(UTC)),
        ConversationMessage("user", "ainda ai?", datetime.now(UTC)),
    ]

    messages = _build_messages("oi de novo", RouteCategory.COURSE_QUESTION, history)

    assert messages[0]["content"] != history[0].text  # wrapped, not raw
    assert messages[1] == {"role": "user", "content": "ainda ai?"}
