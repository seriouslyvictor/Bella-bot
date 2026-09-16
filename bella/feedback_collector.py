"""Adaptive feedback gathering state machine and extraction engine."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
import logging
from pathlib import Path
import re
from typing import TYPE_CHECKING, Any

from google import genai
from google.genai import types
from pydantic import BaseModel

from bella.app_registry import DEFAULT_APP_ID

if TYPE_CHECKING:
    from bella.conversation_store import ConversationMessage, ConversationStore

logger = logging.getLogger("bella")

DEFAULT_AGENT_MODEL = "gemini-3.8-flash"


class FeedbackPhase(StrEnum):
    IDLE = "idle"
    COLLECTING = "collecting"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


@dataclass(frozen=True)
class FeedbackDraft:
    app_id: str
    title: str
    observed: str
    expected: str
    evidence: str = ""
    is_complete: bool = False


@dataclass(frozen=True)
class FeedbackResult:
    reply_text: str
    phase: FeedbackPhase
    draft: FeedbackDraft | None
    confirmed: bool = False
    cancelled: bool = False
    staged_id: int | None = None


class ExtractedFeedback(BaseModel):
    title: str
    observed: str
    expected: str
    evidence: str = ""
    is_complete: bool
    follow_up_question: str = ""


_CONFIRM_KEYWORDS = {
    "sim",
    "s",
    "confirmo",
    "confirmado",
    "confirmar",
    "pode enviar",
    "pode criar",
    "pode mandar",
    "ok",
    "correto",
    "positivo",
    "está certo",
    "esta certo",
    "tá certo",
    "ta certo",
    "perfeito",
    "isso",
    "exato",
    "bora",
    "com certeza",
    "yes",
    "y",
    "send",
    "confirm",
}

_CANCEL_KEYWORDS = {
    "não",
    "nao",
    "n",
    "cancela",
    "cancelar",
    "cancelado",
    "deixa pra lá",
    "deixa pra la",
    "esquece",
    "desisto",
    "abortar",
    "parar",
    "não precisa",
    "nao precisa",
    "no",
    "cancel",
}


def is_confirmation(text: str) -> bool:
    cleaned = re.sub(r"[^\w\s]", "", text.strip().lower())
    if cleaned in _CONFIRM_KEYWORDS:
        return True
    words = cleaned.split()
    if any(w in ("não", "nao", "nunca", "cancelar", "cancela") for w in words):
        return False
    return any(cleaned.startswith(k + " ") or cleaned == k for k in _CONFIRM_KEYWORDS)


def is_cancellation(text: str) -> bool:
    raw = text.strip().lower()
    cleaned = re.sub(r"[^\w\s]", "", raw)
    if cleaned in _CANCEL_KEYWORDS:
        return True
    if re.search(r"\bn[aã]o\s+cancela\b", raw):
        return False
    words = cleaned.split()
    if any(
        w in ("cancela", "cancelar", "cancelado", "esquece", "desisto", "abortar")
        for w in words
    ):
        return True
    return any(cleaned.startswith(k + " ") for k in _CANCEL_KEYWORDS)


def format_draft_summary(
    draft: FeedbackDraft, app_name: str = "Report Generator 9000"
) -> str:
    lines = [
        f"Preparei um rascunho do seu relato para o aplicativo *{app_name}*:\n",
        f"📋 *Título:* {draft.title}",
        f"🔍 *O que aconteceu:* {draft.observed}",
        f"🎯 *O que era esperado:* {draft.expected}",
    ]
    if draft.evidence:
        lines.append(f"📎 *Detalhes / Evidências:* {draft.evidence}")
    lines.append(
        "\nVocê confirma o envio deste ticket? "
        '(Responda com *"Sim"* para confirmar, me diga o que deseja alterar, ou *"Cancelar"* para desistir)'
    )
    return "\n".join(lines)


EXTRACTION_PROMPT_TEMPLATE = """You are Nova's structured feedback extractor for the application '{app_id}'.
Your task is to analyze user messages and extract/refine bug report or feature request details into structured format.

Current draft details (if any):
- Title: {current_title}
- Observed Behavior: {current_observed}
- Expected Behavior: {current_expected}
- Evidence/Details: {current_evidence}

User input to incorporate:
<user_message>
{user_message}
</user_message>

Guidelines:
1. title: A concise, descriptive summary of the issue in Portuguese (e.g. "Erro na conversão de PDF para Loja Virtual").
2. observed: What happened, what error occurred, or what is malfunctioning.
3. expected: What should happen, what the user expected, or the desired feature.
4. evidence: Any spreadsheet, row, error message, URL, or technical details provided.
5. is_complete: Set to TRUE if BOTH observed behavior AND sufficient context (e.g. expected behavior or clear problem description) are present to form an actionable ticket.
   Set to FALSE if the user provided vague or incomplete information (e.g., just "deu erro", "não funciona", "problema na planilha") that requires follow-up.
6. follow_up_question: If is_complete is FALSE, provide a polite, natural question in Portuguese asking specifically for the missing details. If is_complete is TRUE, this can be empty.
"""


class FeedbackCollector:
    def __init__(
        self,
        client: genai.Client,
        app_id: str = DEFAULT_APP_ID,
        app_name: str = "Report Generator 9000",
        model: str = DEFAULT_AGENT_MODEL,
        inbox_path: Path | None = None,
    ) -> None:
        self._client = client
        self._app_id = app_id
        self._app_name = app_name
        self._model = model
        self._inbox_path = inbox_path

    async def extract_draft(
        self, text: str, current_draft: FeedbackDraft | None = None
    ) -> ExtractedFeedback:
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(
            app_id=self._app_id,
            current_title=current_draft.title if current_draft else "Nenhum",
            current_observed=current_draft.observed if current_draft else "Nenhum",
            current_expected=current_draft.expected if current_draft else "Nenhum",
            current_evidence=current_draft.evidence if current_draft else "Nenhum",
            user_message=text,
        )

        config = types.GenerateContentConfig(
            system_instruction=prompt,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=ExtractedFeedback,
        )

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=text,
            config=config,
        )

        if response is None:
            raise ValueError("Feedback extractor returned no response")

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, ExtractedFeedback):
            return parsed

        text_content = getattr(response, "text", None)
        if not text_content:
            raise ValueError("Feedback extractor returned an empty response")

        return ExtractedFeedback.model_validate_json(text_content)

    async def process_turn(
        self,
        phone_number: str,
        text: str,
        store: "ConversationStore",
        history: Sequence["ConversationMessage"] | None = None,
    ) -> FeedbackResult:
        phase, draft = await store.get_feedback_draft(phone_number)

        # 1. Handling cancellation at any active phase
        if phase in (FeedbackPhase.AWAITING_CONFIRMATION, FeedbackPhase.COLLECTING):
            if is_cancellation(text):
                await store.clear_feedback_draft(phone_number)
                return FeedbackResult(
                    reply_text=(
                        "Entendido, o relato foi cancelado! "
                        "Se precisar de mais alguma coisa, estou à disposição 😊"
                    ),
                    phase=FeedbackPhase.IDLE,
                    draft=None,
                    cancelled=True,
                )

        # 2. In AWAITING_CONFIRMATION phase
        if phase == FeedbackPhase.AWAITING_CONFIRMATION and draft is not None:
            if is_confirmation(text):
                await store.clear_feedback_draft(phone_number)
                staged_id = await store.stage_feedback(phone_number, draft)
                if self._inbox_path is not None:
                    from bella.inbox_writer import append_to_inbox

                    try:
                        append_to_inbox(self._inbox_path, draft, phone_number)
                    except Exception as e:
                        logger.warning(
                            "failed to append feedback to inbox %s: %s",
                            self._inbox_path,
                            e,
                        )
                return FeedbackResult(
                    reply_text=(
                        f"Perfeito! Seu relato sobre o *{self._app_name}* foi confirmado e registrado com sucesso. "
                        "Nossa equipe técnica já está com as informações para análise. Muito obrigado pelo feedback! 🚀"
                    ),
                    phase=FeedbackPhase.IDLE,
                    draft=draft,
                    confirmed=True,
                    staged_id=staged_id,
                )
            # If user provides adjustments or new info
            extracted = await self.extract_draft(text, current_draft=draft)
            updated_draft = FeedbackDraft(
                app_id=self._app_id,
                title=extracted.title or draft.title,
                observed=extracted.observed or draft.observed,
                expected=extracted.expected or draft.expected,
                evidence=extracted.evidence or draft.evidence,
                is_complete=True,
            )
            await store.set_feedback_draft(
                phone_number, FeedbackPhase.AWAITING_CONFIRMATION, updated_draft
            )
            return FeedbackResult(
                reply_text=format_draft_summary(updated_draft, self._app_name),
                phase=FeedbackPhase.AWAITING_CONFIRMATION,
                draft=updated_draft,
            )

        # 3. In IDLE or COLLECTING phase
        extracted = await self.extract_draft(text, current_draft=draft)
        if extracted.is_complete:
            new_draft = FeedbackDraft(
                app_id=self._app_id,
                title=extracted.title,
                observed=extracted.observed,
                expected=extracted.expected,
                evidence=extracted.evidence,
                is_complete=True,
            )
            await store.set_feedback_draft(
                phone_number, FeedbackPhase.AWAITING_CONFIRMATION, new_draft
            )
            return FeedbackResult(
                reply_text=format_draft_summary(new_draft, self._app_name),
                phase=FeedbackPhase.AWAITING_CONFIRMATION,
                draft=new_draft,
            )

        # Still missing details
        collecting_draft = FeedbackDraft(
            app_id=self._app_id,
            title=extracted.title,
            observed=extracted.observed,
            expected=extracted.expected,
            evidence=extracted.evidence,
            is_complete=False,
        )
        await store.set_feedback_draft(
            phone_number, FeedbackPhase.COLLECTING, collecting_draft
        )
        question = (
            extracted.follow_up_question
            or "Poderia me detalhar o que aconteceu e o que era esperado?"
        )
        return FeedbackResult(
            reply_text=question,
            phase=FeedbackPhase.COLLECTING,
            draft=collecting_draft,
        )
