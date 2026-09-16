"""Scope Gate contract and routing categories.

The category values are a stable routing contract: tickets 05, 07, and 08
build their answering, apostila, and handoff behavior on these exact labels.
"""

from enum import StrEnum
from typing import Protocol


class RouteCategory(StrEnum):
    APP_FEEDBACK = "app_feedback"
    APP_SUPPORT = "app_support"
    GREETING = "greeting"
    HUMAN_REQUESTED = "human_requested"
    OUT_OF_SCOPE = "out_of_scope"

    # Backward-compatibility aliases for legacy tests/modules
    COURSE_QUESTION = "course_question"
    APOSTILA_REQUEST = "apostila_request"
    ENROLLMENT_QUESTION = "enrollment_question"
    ABOUT_BELLA = "about_bella"


class ScopeGate(Protocol):
    async def classify(self, text: str) -> RouteCategory: ...

