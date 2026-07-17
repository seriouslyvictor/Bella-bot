"""Unit tests for the source-agnostic Control Channel parser.

Behavioral coverage (pause cleared, reply sent, ordering vs. the Scope Gate)
lives in tests/test_webhook.py through the webhook seam; this file only
exercises the format-tolerance matrix for parse_command in isolation.
"""

import pytest

from bella.control_channel import VoltarCommand, parse_command


@pytest.mark.parametrize(
    "text",
    [
        "voltar 5511999999999",
        "Voltar 5511999999999",
        "VOLTAR 5511999999999",
        "  voltar   5511999999999  ",
        "voltar +55 (11) 99999-9999",
        "voltar +55 11 99999-9999",
        "voltar 55-11-99999-9999",
    ],
)
def test_parses_formatted_numbers_to_digits_only(text: str) -> None:
    assert parse_command(text) == VoltarCommand("5511999999999")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "oi bella",
        "voltar",
        "voltar ",
        "voltarei amanha",
        "por favor voltar 5511999999999",
        "voltar sem numero",
    ],
)
def test_unrecognized_text_returns_none(text: str) -> None:
    assert parse_command(text) is None
