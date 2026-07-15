"""Scope Gate contract and routing categories.

The category values are a stable routing contract: tickets 05, 07, and 08
build their answering, apostila, and handoff behavior on these exact labels.
"""

from enum import StrEnum
from typing import Protocol


class RouteCategory(StrEnum):
    COURSE_QUESTION = "course_question"
    APOSTILA_REQUEST = "apostila_request"
    ENROLLMENT_QUESTION = "enrollment_question"
    GREETING = "greeting"
    ABOUT_BELLA = "about_bella"
    HUMAN_REQUESTED = "human_requested"
    OUT_OF_SCOPE = "out_of_scope"


class ScopeGate(Protocol):
    async def classify(self, text: str) -> RouteCategory: ...

