from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from google import genai

from bella.conversation_store import InMemoryConversationStore
from bella.feedback_collector import (
    ExtractedFeedback,
    FeedbackCollector,
    FeedbackDraft,
    FeedbackPhase,
    format_draft_summary,
    is_cancellation,
    is_confirmation,
)


class FakeResponse:
    def __init__(self, text: str | None = None, parsed: Any = None) -> None:
        self.text = text
        self.parsed = parsed


def make_collector(
    response: Any = None,
    side_effect: Exception | None = None,
    app_id: str = "report_generator9000",
    app_name: str = "Report Generator 9000",
) -> tuple[FeedbackCollector, AsyncMock]:
    mock_client = MagicMock(spec=genai.Client)
    mock_client.aio = MagicMock()
    mock_client.aio.models = MagicMock()
    mock_generate = AsyncMock()
    if side_effect:
        mock_generate.side_effect = side_effect
    else:
        mock_generate.return_value = response
    mock_client.aio.models.generate_content = mock_generate
    collector = FeedbackCollector(
        cast(genai.Client, mock_client),
        app_id=app_id,
        app_name=app_name,
    )
    return collector, mock_generate


def test_confirmation_matcher() -> None:
    assert is_confirmation("sim") is True
    assert is_confirmation("Sim, pode enviar") is True
    assert is_confirmation("confirmo!") is True
    assert is_confirmation("pode criar o ticket") is True
    assert is_confirmation("ok") is True
    assert is_confirmation("não quero") is False
    assert is_confirmation("ainda não") is False


def test_cancellation_matcher() -> None:
    assert is_cancellation("cancela") is True
    assert is_cancellation("cancelar por favor") is True
    assert is_cancellation("não") is True
    assert is_cancellation("deixa pra lá") is True
    assert is_cancellation("esquece") is True
    assert is_cancellation("sim") is False


def test_format_draft_summary() -> None:
    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Erro no Playwright",
        observed="Timeout ao abrir site",
        expected="Site capturado",
        evidence="Pasta 115-2026",
        is_complete=True,
    )
    summary = format_draft_summary(draft, "Report Generator 9000")
    assert "Report Generator 9000" in summary
    assert "Erro no Playwright" in summary
    assert "Timeout ao abrir site" in summary
    assert "Pasta 115-2026" in summary
    assert "Você confirma o envio deste ticket?" in summary


@pytest.mark.anyio
async def test_single_turn_extraction_transitions_directly_to_awaiting_confirmation() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"

    extracted = ExtractedFeedback(
        title="Timeout de captura no Playwright para pasta 115-2026",
        observed="Ocorreu timeout durante a captura da página home",
        expected="Páginas capturadas normalmente",
        evidence="Pasta 115-2026",
        is_complete=True,
    )
    collector, _ = make_collector(response=FakeResponse(parsed=extracted))

    result = await collector.process_turn(
        phone,
        "Ao gerar o relatório da pasta 115-2026, deu timeout na captura da home mas o site estava online.",
        store,
    )

    assert result.phase == FeedbackPhase.AWAITING_CONFIRMATION
    assert result.confirmed is False
    assert result.cancelled is False
    assert result.draft is not None
    assert result.draft.title == "Timeout de captura no Playwright para pasta 115-2026"
    assert "Você confirma o envio" in result.reply_text

    # Verify persisted in store
    phase, stored_draft = await store.get_feedback_draft(phone)
    assert phase == FeedbackPhase.AWAITING_CONFIRMATION
    assert stored_draft == result.draft


@pytest.mark.anyio
async def test_vague_initial_message_clarifies_in_collecting_then_confirms() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"

    # Turn 1: Vague
    vague_extracted = ExtractedFeedback(
        title="Erro na geração",
        observed="Erro genérico",
        expected="",
        evidence="",
        is_complete=False,
        follow_up_question="Poderia me detalhar qual foi o erro observado e em qual pasta?",
    )
    collector, mock_gen = make_collector(response=FakeResponse(parsed=vague_extracted))

    result_turn1 = await collector.process_turn(phone, "Deu erro no sistema", store)

    assert result_turn1.phase == FeedbackPhase.COLLECTING
    assert result_turn1.confirmed is False
    assert result_turn1.reply_text == "Poderia me detalhar qual foi o erro observado e em qual pasta?"

    phase1, draft1 = await store.get_feedback_draft(phone)
    assert phase1 == FeedbackPhase.COLLECTING
    assert draft1 is not None
    assert draft1.is_complete is False

    # Turn 2: Providing details
    complete_extracted = ExtractedFeedback(
        title="Falha de coluna na planilha da pasta 200-2026",
        observed="Coluna Especialista ausente",
        expected="Planilha lida com sucesso",
        evidence="Pasta 200-2026",
        is_complete=True,
    )
    mock_gen.return_value = FakeResponse(parsed=complete_extracted)

    result_turn2 = await collector.process_turn(
        phone,
        "A planilha da pasta 200-2026 não tinha a coluna Especialista e o sistema travou",
        store,
    )

    assert result_turn2.phase == FeedbackPhase.AWAITING_CONFIRMATION
    assert result_turn2.confirmed is False
    assert "Você confirma o envio" in result_turn2.reply_text

    phase2, draft2 = await store.get_feedback_draft(phone)
    assert phase2 == FeedbackPhase.AWAITING_CONFIRMATION
    assert draft2 is not None
    assert draft2.is_complete is True


@pytest.mark.anyio
async def test_explicit_confirmation_resets_state_and_returns_confirmed() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"

    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Erro na conversão PDF",
        observed="LibreOffice travou",
        expected="PDF gerado",
        evidence="Pasta 115",
        is_complete=True,
    )
    await store.set_feedback_draft(phone, FeedbackPhase.AWAITING_CONFIRMATION, draft)

    collector, _ = make_collector()

    result = await collector.process_turn(phone, "Sim, confirmo", store)

    assert result.phase == FeedbackPhase.IDLE
    assert result.confirmed is True
    assert result.cancelled is False
    assert result.draft == draft
    assert "confirmado e registrado com sucesso" in result.reply_text

    # Store cleared
    phase, stored_draft = await store.get_feedback_draft(phone)
    assert phase == FeedbackPhase.IDLE
    assert stored_draft is None


@pytest.mark.anyio
async def test_cancellation_in_awaiting_confirmation_clears_state() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"

    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Erro na conversão PDF",
        observed="LibreOffice travou",
        expected="PDF gerado",
        evidence="Pasta 115",
        is_complete=True,
    )
    await store.set_feedback_draft(phone, FeedbackPhase.AWAITING_CONFIRMATION, draft)

    collector, _ = make_collector()

    result = await collector.process_turn(phone, "Não, cancela por favor", store)

    assert result.phase == FeedbackPhase.IDLE
    assert result.confirmed is False
    assert result.cancelled is True
    assert result.draft is None
    assert "cancelado" in result.reply_text

    phase, stored_draft = await store.get_feedback_draft(phone)
    assert phase == FeedbackPhase.IDLE
    assert stored_draft is None


@pytest.mark.anyio
async def test_cancellation_during_collecting_clears_state() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"

    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Erro vago",
        observed="Erro",
        expected="",
        is_complete=False,
    )
    await store.set_feedback_draft(phone, FeedbackPhase.COLLECTING, draft)

    collector, _ = make_collector()

    result = await collector.process_turn(phone, "esquece", store)

    assert result.phase == FeedbackPhase.IDLE
    assert result.cancelled is True
    assert result.confirmed is False

    phase, stored_draft = await store.get_feedback_draft(phone)
    assert phase == FeedbackPhase.IDLE
    assert stored_draft is None


@pytest.mark.anyio
async def test_modification_while_awaiting_confirmation_updates_draft() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"

    initial_draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Erro no Playwright",
        observed="Timeout na home",
        expected="Captura completa",
        evidence="Pasta 115",
        is_complete=True,
    )
    await store.set_feedback_draft(
        phone, FeedbackPhase.AWAITING_CONFIRMATION, initial_draft
    )

    updated_extracted = ExtractedFeedback(
        title="Erro no Playwright na pasta 120",
        observed="Timeout na home",
        expected="Captura completa",
        evidence="Pasta 120 (e não 115)",
        is_complete=True,
    )
    collector, _ = make_collector(response=FakeResponse(parsed=updated_extracted))

    result = await collector.process_turn(
        phone,
        "Na verdade era na pasta 120 e não 115",
        store,
    )

    assert result.phase == FeedbackPhase.AWAITING_CONFIRMATION
    assert result.confirmed is False
    assert result.draft is not None
    assert result.draft.title == "Erro no Playwright na pasta 120"
    assert "Pasta 120" in result.draft.evidence

    phase, stored_draft = await store.get_feedback_draft(phone)
    assert phase == FeedbackPhase.AWAITING_CONFIRMATION
    assert stored_draft == result.draft


@pytest.mark.anyio
async def test_in_memory_store_draft_persistence_lifecycle() -> None:
    store = InMemoryConversationStore()
    phone = "5511888888888"

    phase, draft = await store.get_feedback_draft(phone)
    assert phase == FeedbackPhase.IDLE
    assert draft is None

    test_draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Teste",
        observed="Obs",
        expected="Exp",
        evidence="Evid",
        is_complete=True,
    )
    await store.set_feedback_draft(phone, FeedbackPhase.COLLECTING, test_draft)

    phase, retrieved = await store.get_feedback_draft(phone)
    assert phase == FeedbackPhase.COLLECTING
    assert retrieved == test_draft

    await store.clear_feedback_draft(phone)
    phase, retrieved_after = await store.get_feedback_draft(phone)
    assert phase == FeedbackPhase.IDLE
    assert retrieved_after is None
