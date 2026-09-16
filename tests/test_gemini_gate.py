from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from google import genai
from google.genai import types

from bella.gemini_gate import GateDecision, GeminiScopeGate
from bella.scope_gate import RouteCategory


class FakeResponse:
    def __init__(self, text: str | None = None, parsed: Any = None) -> None:
        self.text = text
        self.parsed = parsed


def make_gate(
    response: Any = None,
    side_effect: Exception | None = None,
    model: str = "gemini-3.8-flash",
) -> tuple[GeminiScopeGate, AsyncMock]:
    mock_client = MagicMock(spec=genai.Client)
    mock_client.aio = MagicMock()
    mock_client.aio.models = MagicMock()
    mock_generate = AsyncMock()
    if side_effect:
        mock_generate.side_effect = side_effect
    else:
        mock_generate.return_value = response
    mock_client.aio.models.generate_content = mock_generate
    gate = GeminiScopeGate(cast(genai.Client, mock_client), model=model)
    return gate, mock_generate


@pytest.mark.anyio
@pytest.mark.parametrize(
    "category",
    [
        RouteCategory.APP_FEEDBACK,
        RouteCategory.APP_SUPPORT,
        RouteCategory.GREETING,
        RouteCategory.HUMAN_REQUESTED,
        RouteCategory.OUT_OF_SCOPE,
    ],
)
async def test_classify_each_category_with_parsed_object(category: RouteCategory) -> None:
    decision = GateDecision(category=category)
    response = FakeResponse(parsed=decision)
    gate, mock_generate = make_gate(response=response)

    result = await gate.classify("User message here")

    assert result == category
    mock_generate.assert_awaited_once()
    _, kwargs = mock_generate.call_args
    assert kwargs["model"] == "gemini-3.8-flash"
    assert kwargs["contents"] == "User message here"
    config = kwargs["config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.response_mime_type == "application/json"
    assert config.response_schema is GateDecision
    assert config.temperature == 0.0


@pytest.mark.anyio
@pytest.mark.parametrize(
    "category",
    [
        RouteCategory.APP_FEEDBACK,
        RouteCategory.APP_SUPPORT,
        RouteCategory.GREETING,
        RouteCategory.HUMAN_REQUESTED,
        RouteCategory.OUT_OF_SCOPE,
    ],
)
async def test_classify_each_category_from_json_text(category: RouteCategory) -> None:
    response = FakeResponse(text=f'{{"category": "{category.value}"}}', parsed=None)
    gate, _ = make_gate(response=response)

    result = await gate.classify("User message")

    assert result == category


@pytest.mark.anyio
async def test_custom_model_configuration() -> None:
    decision = GateDecision(category=RouteCategory.APP_SUPPORT)
    response = FakeResponse(parsed=decision)
    gate, mock_generate = make_gate(response=response, model="custom-gemini-model")

    result = await gate.classify("Como usar o app?")

    assert result == RouteCategory.APP_SUPPORT
    _, kwargs = mock_generate.call_args
    assert kwargs["model"] == "custom-gemini-model"


@pytest.mark.anyio
async def test_api_error_raises_exception() -> None:
    gate, _ = make_gate(side_effect=RuntimeError("Google GenAI API connection failure"))

    with pytest.raises(RuntimeError, match="Google GenAI API connection failure"):
        await gate.classify("Oi")


@pytest.mark.anyio
async def test_empty_response_raises_value_error() -> None:
    response = FakeResponse(text="", parsed=None)
    gate, _ = make_gate(response=response)

    with pytest.raises(ValueError, match="Scope Gate returned no structured decision"):
        await gate.classify("Oi")


@pytest.mark.anyio
async def test_none_response_text_raises_value_error() -> None:
    response = FakeResponse(text=None, parsed=None)
    gate, _ = make_gate(response=response)

    with pytest.raises(ValueError, match="Scope Gate returned no structured decision"):
        await gate.classify("Oi")


@pytest.mark.anyio
async def test_invalid_json_raises_validation_error() -> None:
    response = FakeResponse(text="not a valid json", parsed=None)
    gate, _ = make_gate(response=response)

    with pytest.raises(Exception):
        await gate.classify("Oi")


@pytest.mark.anyio
async def test_unknown_category_in_json_raises_validation_error() -> None:
    response = FakeResponse(text='{"category": "non_existent_category"}', parsed=None)
    gate, _ = make_gate(response=response)

    with pytest.raises(Exception):
        await gate.classify("Oi")
