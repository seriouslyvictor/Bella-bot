from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from google import genai
from google.genai import types

from bella.app_registry import AppConfig
from bella.conversation_store import ConversationMessage
from bella.gemini_answerer import (
    GeminiSupportAnswerer,
    SupportAnswerPayload,
    _build_contents,
)
from bella.scope_gate import RouteCategory


class FakeResponse:
    def __init__(self, text: str | None = None, parsed: Any = None) -> None:
        self.text = text
        self.parsed = parsed


def make_answerer(
    response: Any = None,
    side_effect: Exception | None = None,
    knowledge_base: str = "O Report Generator 9000 suporta os temas WebSite e Loja Virtual.",
    model: str = "gemini-3.8-flash",
) -> tuple[GeminiSupportAnswerer, AsyncMock]:
    mock_client = MagicMock(spec=genai.Client)
    mock_client.aio = MagicMock()
    mock_client.aio.models = MagicMock()
    mock_generate = AsyncMock()
    if side_effect:
        mock_generate.side_effect = side_effect
    else:
        mock_generate.return_value = response
    mock_client.aio.models.generate_content = mock_generate

    app_config = AppConfig(
        app_id="report_generator9000",
        name="Report Generator 9000",
        description="Gerador de Relatórios",
        repo="seriouslyvictor/report_generator9000",
        knowledge_base=knowledge_base,
    )
    answerer = GeminiSupportAnswerer(
        cast(genai.Client, mock_client),
        app_config=app_config,
        model=model,
    )
    return answerer, mock_generate


@pytest.mark.anyio
async def test_grounded_question_returns_answer_without_handoff() -> None:
    payload = SupportAnswerPayload(
        answer="O sistema suporta os temas Inserção digital - Desenvolvimento de WebSite e Implantação de Loja Virtual.",
        needs_handoff=False,
    )
    answerer, mock_generate = make_answerer(response=FakeResponse(parsed=payload))

    result = await answerer.answer(
        "Quais temas são suportados?",
        RouteCategory.APP_SUPPORT,
        history=[],
    )

    assert result.text == (
        "O sistema suporta os temas Inserção digital - Desenvolvimento de WebSite e Implantação de Loja Virtual."
    )
    assert result.needs_handoff is False
    mock_generate.assert_awaited_once()


@pytest.mark.anyio
async def test_unknown_question_produces_honest_deflection_with_handoff() -> None:
    payload = SupportAnswerPayload(
        answer="Não encontrei essa informação na documentação oficial. Vou encaminhar sua dúvida para nossa equipe humana.",
        needs_handoff=True,
    )
    answerer, _ = make_answerer(response=FakeResponse(parsed=payload))

    result = await answerer.answer(
        "Como integrar com o SAP?",
        RouteCategory.APP_SUPPORT,
        history=[],
    )

    assert result.needs_handoff is True
    assert "Não encontrei essa informação" in result.text


@pytest.mark.anyio
async def test_json_text_fallback_parsing() -> None:
    json_text = '{"answer": "O relatório possui 9 etapas.", "needs_handoff": false}'
    answerer, _ = make_answerer(response=FakeResponse(text=json_text, parsed=None))

    result = await answerer.answer(
        "Quantas etapas tem o pipeline?",
        RouteCategory.APP_SUPPORT,
        history=[],
    )

    assert result.text == "O relatório possui 9 etapas."
    assert result.needs_handoff is False


@pytest.mark.anyio
async def test_empty_response_raises_value_error() -> None:
    answerer, _ = make_answerer(response=FakeResponse(text="", parsed=None))

    with pytest.raises(ValueError, match="empty response"):
        await answerer.answer(
            "Ajuda",
            RouteCategory.APP_SUPPORT,
            history=[],
        )


@pytest.mark.anyio
async def test_empty_answer_field_raises_value_error() -> None:
    payload = SupportAnswerPayload(answer="   ", needs_handoff=False)
    answerer, _ = make_answerer(response=FakeResponse(parsed=payload))

    with pytest.raises(ValueError, match="empty answer"):
        await answerer.answer(
            "Ajuda",
            RouteCategory.APP_SUPPORT,
            history=[],
        )


def test_build_contents_frames_history_and_markers() -> None:
    now = datetime.now(UTC)
    history = [
        ConversationMessage(role="user", text="Olá", timestamp=now),
        ConversationMessage(
            role="assistant", text="Olá! Como posso ajudar?", timestamp=now
        ),
        ConversationMessage(
            role="owner", text="Vou verificar seu relatório agora", timestamp=now
        ),
    ]

    contents = _build_contents("Obrigado", RouteCategory.APP_SUPPORT, history)

    assert len(contents) == 4
    # User turn
    assert contents[0].role == "user"
    assert contents[0].parts is not None
    assert "<user_message>\nOlá\n</user_message>" in (contents[0].parts[0].text or "")
    # Assistant turn mapped to model role
    assert contents[1].role == "model"
    assert contents[1].parts is not None
    assert contents[1].parts[0].text == "Olá! Como posso ajudar?"
    # Owner turn wrapped in <owner_message> and mapped to user role
    assert contents[2].role == "user"
    assert contents[2].parts is not None
    assert "<owner_message>\nVou verificar seu relatório agora\n</owner_message>" in (
        contents[2].parts[0].text or ""
    )
    # Latest turn
    assert contents[3].role == "user"
    assert contents[3].parts is not None
    assert "Intent: app_support" in (contents[3].parts[0].text or "")
    assert "<user_message>\nObrigado\n</user_message>" in (contents[3].parts[0].text or "")
