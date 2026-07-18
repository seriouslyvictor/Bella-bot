import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

import pytest

from bella.anthropic_answerer import _build_system
from bella.availability import AvailabilityError
from bella.config import Settings
from bella.course_content import CourseContent
from bella.seat_count import SeatCountHolder, SeatCountRefresher
from tests.conftest import FakeSender, make_test_client


class FakeAvailabilitySource:
    def __init__(
        self,
        results: Sequence[int | Exception],
        *,
        called: Event | None = None,
    ) -> None:
        self._results = iter(results)
        self.called = called
        self.fetches = 0
        self.closed = False

    async def fetch_count(self) -> int:
        self.fetches += 1
        if self.called is not None:
            self.called.set()
        result = next(self._results)
        if isinstance(result, Exception):
            raise result
        return result

    async def close(self) -> None:
        self.closed = True


def _content_with_holder(
    tmp_path: Path,
    holder: SeatCountHolder,
) -> CourseContent:
    knowledge_base = tmp_path / "knowledge-base.md"
    knowledge_base.write_text("Curso público.", encoding="utf-8")
    enrollment_card = tmp_path / "enrollment-card.yaml"
    enrollment_card.write_text(
        "\n".join(
            [
                'course_name: "Curso"',
                'enrollment_url: "https://example.test/inscricao"',
                'senai_course_listing_url: "https://example.test/cursos"',
                'human_contact: "SENAI"',
                'human_contact_phone: ""',
                'owner_contact: ""',
            ]
        ),
        encoding="utf-8",
    )
    return CourseContent.from_files(
        knowledge_base,
        enrollment_card,
        seat_count_holder=holder,
    )


def test_fresh_live_count_is_rendered_per_answer(tmp_path: Path) -> None:
    now = [datetime(2026, 7, 18, 12, 0, tzinfo=UTC)]
    holder = SeatCountHolder(
        max_age=timedelta(hours=24),
        clock=lambda: now[0],
    )
    content = _content_with_holder(tmp_path, holder)

    before = _build_system(content)[-1]["text"]
    holder.update(20)
    after = _build_system(content)[-1]["text"]

    assert "seats:" not in before
    assert "seats: 20 vagas" in after


def test_single_seat_uses_singular_wording(tmp_path: Path) -> None:
    holder = SeatCountHolder(max_age=timedelta(hours=24))
    content = _content_with_holder(tmp_path, holder)

    holder.update(1)

    assert "seats: 1 vaga\n" in content.render_enrollment_card()


def test_rendered_enrollment_card_excludes_the_listing_url(tmp_path: Path) -> None:
    # The answerer may only ever emit enrollment_url (see PERSONA_AND_RULES);
    # senai_course_listing_url is operational-only and must never reach the
    # model's context as a second URL.
    holder = SeatCountHolder(max_age=timedelta(hours=24))
    content = _content_with_holder(tmp_path, holder)

    rendered = content.render_enrollment_card()

    assert content.senai_course_listing_url not in rendered
    assert "senai_course_listing_url" not in rendered
    assert content.enrollment_url in rendered


def test_empty_or_stale_count_is_absent_from_enrollment_card(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 7, 18, 12, 0, tzinfo=UTC)]
    holder = SeatCountHolder(
        max_age=timedelta(hours=24),
        clock=lambda: now[0],
    )
    content = _content_with_holder(tmp_path, holder)
    assert "seats:" not in content.render_enrollment_card()

    holder.update(18)
    now[0] += timedelta(hours=24, seconds=1)

    assert "seats:" not in content.render_enrollment_card()


def test_maximum_seat_count_age_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = {
        "EVOLUTION_URL": "http://evolution-go:8080",
        "EVOLUTION_API_KEY": "token",
        "EVOLUTION_INSTANCE_ID": "instance",
        "BELLA_INTERNAL_URL": "http://bella:8000",
        "ANTHROPIC_API_KEY": "key",
        "BELLA_DATABASE_URL": "postgresql://bella:pw@postgres/bella",
        "ADMIN_CONTACT": "5511999999999",
        "SEAT_COUNT_MAX_AGE_SECONDS": "7200",
    }
    for key, value in required.items():
        monkeypatch.setenv(key, value)

    assert Settings.from_env().seat_count_max_age_seconds == 7200


def test_shipped_enrollment_card_has_no_hand_edited_seats() -> None:
    card = (
        Path(__file__).resolve().parent.parent / "content" / "enrollment_card.yaml"
    ).read_text(encoding="utf-8")

    assert "\nseats:" not in card
    assert "\nsenai_course_listing_url:" in card


def test_refresher_keeps_last_good_count_until_it_becomes_stale(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 7, 18, 12, 0, tzinfo=UTC)]
    holder = SeatCountHolder(
        max_age=timedelta(hours=24),
        clock=lambda: now[0],
    )
    content = _content_with_holder(tmp_path, holder)
    source = FakeAvailabilitySource(
        [20, AvailabilityError("temporary outage")]
    )
    refresher = SeatCountRefresher(source, holder, interval_seconds=21_600)

    assert asyncio.run(refresher.refresh_once()) is True
    now[0] += timedelta(hours=6)
    assert asyncio.run(refresher.refresh_once()) is False
    assert "seats: 20 vagas" in content.render_enrollment_card()

    now[0] += timedelta(hours=18, seconds=1)
    assert "seats:" not in content.render_enrollment_card()


def test_refresher_repeats_on_the_configured_interval() -> None:
    holder = SeatCountHolder(max_age=timedelta(hours=24))
    source = FakeAvailabilitySource([20, 19])
    intervals: list[float] = []

    async def controlled_sleep(seconds: float) -> None:
        intervals.append(seconds)
        if len(intervals) > 1:
            raise asyncio.CancelledError

    refresher = SeatCountRefresher(
        source,
        holder,
        interval_seconds=21_600,
        sleep=controlled_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(refresher.run())

    assert source.fetches == 2
    assert intervals == [21_600, 21_600]
    assert holder.current_count() == 19


def test_failed_refresh_logs_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    holder = SeatCountHolder(max_age=timedelta(hours=24))
    source = FakeAvailabilitySource(
        [AvailabilityError("course row missing")]
    )
    refresher = SeatCountRefresher(source, holder, interval_seconds=21_600)

    with caplog.at_level(logging.WARNING, logger="bella"):
        assert asyncio.run(refresher.refresh_once()) is False

    assert "seat count refresh failed" in caplog.text
    assert "course row missing" in caplog.text


def test_refresher_starts_with_application_lifespan() -> None:
    called = Event()
    holder = SeatCountHolder(max_age=timedelta(hours=24))
    source = FakeAvailabilitySource([20], called=called)
    refresher = SeatCountRefresher(source, holder, interval_seconds=21_600)

    with make_test_client(
        FakeSender(),
        seat_count_refresher=refresher,
    ):
        assert called.wait(timeout=1)

    assert holder.current_count() == 20
    assert source.closed is True


def test_refresh_defaults_and_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    required = {
        "EVOLUTION_URL": "http://evolution-go:8080",
        "EVOLUTION_API_KEY": "token",
        "EVOLUTION_INSTANCE_ID": "instance",
        "BELLA_INTERNAL_URL": "http://bella:8000",
        "ANTHROPIC_API_KEY": "key",
        "BELLA_DATABASE_URL": "postgresql://bella:pw@postgres/bella",
        "ADMIN_CONTACT": "5511999999999",
    }
    for key, value in required.items():
        monkeypatch.setenv(key, value)

    defaults = Settings.from_env()
    assert defaults.seat_count_refresh_seconds == 21_600
    assert defaults.seat_count_max_age_seconds == 86_400

    monkeypatch.setenv("SEAT_COUNT_REFRESH_SECONDS", "3600")
    monkeypatch.setenv("SEAT_COUNT_MAX_AGE_SECONDS", "7200")
    overridden = Settings.from_env()
    assert overridden.seat_count_refresh_seconds == 3600
    assert overridden.seat_count_max_age_seconds == 7200
