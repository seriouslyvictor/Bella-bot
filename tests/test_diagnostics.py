"""The self-test is what an operator has instead of the container logs.

These tests pin the two things that makes it worth having: a failing
dependency is named along with its real exception, and one broken leg does
not hide the others.
"""

import asyncio
from typing import cast

from bella.conversation_store import InMemoryConversationStore
from bella.diagnostics import SelfTest, describe_error, format_report
from bella.evolution import WhatsAppSender
from bella.pipeline import Answerer
from bella.scope_gate import ScopeGate
from tests.conftest import FakeAnswerer, FakeScopeGate, FakeSender


def make_self_test(
    *,
    unhealthy_sender: bool = False,
    failing_gate: bool = False,
    failing_answerer: bool = False,
) -> SelfTest:
    return SelfTest(
        InMemoryConversationStore(),
        cast(WhatsAppSender, FakeSender(unhealthy=unhealthy_sender)),
        cast(ScopeGate, FakeScopeGate(fail=failing_gate)),
        cast(Answerer, FakeAnswerer(fail=failing_answerer)),
    )


def test_describe_error_carries_class_and_message() -> None:
    assert describe_error(RuntimeError("boom")) == "RuntimeError: boom"
    assert describe_error(RuntimeError()) == "RuntimeError"


def test_a_healthy_stack_reports_every_probe_ok() -> None:
    results = asyncio.run(make_self_test().run())

    assert [result.name for result in results] == [
        "banco de dados",
        "whatsapp",
        "modelo roteador",
        "modelo agente",
    ]
    assert all(result.ok for result in results)
    assert "Tudo respondendo normalmente." in format_report(results)


def test_a_failing_model_is_named_with_its_error() -> None:
    results = asyncio.run(make_self_test(failing_answerer=True).run())
    report = format_report(results)

    agent = next(result for result in results if result.name == "modelo agente")
    assert not agent.ok
    assert agent.detail == "RuntimeError: simulated answering failure"
    assert "Falhando: modelo agente." in report
    # The working legs still report, so the report locates the fault.
    assert "✅ *modelo roteador*" in report


def test_probes_are_independent() -> None:
    results = asyncio.run(
        make_self_test(unhealthy_sender=True, failing_gate=True).run()
    )
    failing = {result.name for result in results if not result.ok}

    assert failing == {"whatsapp", "modelo roteador"}
