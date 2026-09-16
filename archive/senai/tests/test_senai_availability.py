import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from bella.availability import AvailabilityError, SenaiAvailabilitySource
from tests.conftest import course_content

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "senai"
LISTING_URL = (
    "https://www.sp.senai.br/cursos/cursos-livres/"
    "tecnologia-da-informacao-e-informatica?unidade=127"
)


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _source(handler: Any, *, class_start: str = "") -> SenaiAvailabilitySource:
    return SenaiAvailabilitySource(
        LISTING_URL,
        class_start=class_start,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def test_source_follows_ver_turmas_and_returns_captured_live_count() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "POST":
            return httpx.Response(200, text=_fixture("class-details.html"))
        if request.url.params.get("pag") == "2":
            return httpx.Response(200, text=_fixture("course-listing-page-2.html"))
        return httpx.Response(200, text=_fixture("course-listing-page-1.html"))

    count = asyncio.run(_source(handler).fetch_count())

    assert count == 20
    assert [request.method for request in seen] == ["GET", "GET", "POST"]
    assert str(seen[-1].url) == "https://www.sp.senai.br/cursosturmas/"
    assert seen[-1].content.decode() == (
        "nomeCurso=inteligencias-artificiais-generativas-aplicada-a-"
        "programacao-chatgpt&cursoId=101299&escolaId=127&"
        "estrategia=Presencial&bolsa=0&gratuito=0&turno=0&pos=0"
    )


def _two_turma_handler(request: httpx.Request) -> httpx.Response:
    if request.method == "POST":
        return httpx.Response(200, text=_fixture("class-details-two-turmas.html"))
    if request.url.params.get("pag") == "2":
        return httpx.Response(200, text=_fixture("course-listing-page-2.html"))
    return httpx.Response(200, text=_fixture("course-listing-page-1.html"))


def test_two_simultaneous_turmas_picks_the_one_matching_class_start() -> None:
    # A next turma opening while the current one still runs is a normal page
    # state, not an anomaly; the Enrollment Card's class_start disambiguates.
    count = asyncio.run(
        _source(_two_turma_handler, class_start="25/07/2026").fetch_count()
    )

    assert count == 20


def test_two_simultaneous_turmas_with_no_class_start_match_fails_and_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The invariant "never a wrong number, degrade to absence" holds even
    # when multiple turmas parse: an unmatched class_start must fail, not
    # guess.
    with caplog.at_level(logging.WARNING, logger="bella"):
        with pytest.raises(AvailabilityError, match="ambiguous"):
            asyncio.run(
                _source(_two_turma_handler, class_start="01/01/2000").fetch_count()
            )

    assert "ambiguous" in caplog.text


@pytest.mark.parametrize(
    ("case", "reason"),
    [
        ("unreachable", "request failed"),
        ("course-missing", "course row missing"),
        ("ver-turmas-missing", "VER TURMAS target missing"),
        ("availability-missing", "availability is unparseable"),
    ],
)
def test_source_anomalies_fail_and_log_warning(
    case: str,
    reason: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if case == "unreachable":
            raise httpx.ConnectError("offline", request=request)
        if request.method == "POST":
            return httpx.Response(200, text="<div>sem disponibilidade</div>")
        if case == "course-missing":
            return httpx.Response(200, text="<div>outro curso</div>")
        if case == "ver-turmas-missing":
            return httpx.Response(
                200,
                text=(
                    "<h5>Inteligências Artificiais Generativas Aplicada "
                    "a Programação - ChatGPT</h5>"
                ),
            )
        return httpx.Response(200, text=_fixture("course-listing-page-2.html"))

    with caplog.at_level(logging.WARNING, logger="bella"):
        with pytest.raises(AvailabilityError, match=reason):
            asyncio.run(_source(handler).fetch_count())

    assert reason in caplog.text


def test_course_listing_url_comes_from_enrollment_card() -> None:
    assert course_content().senai_course_listing_url == LISTING_URL
