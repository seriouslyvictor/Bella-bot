"""Live SENAI seat-count cache and freshness policy."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from bella.availability import AvailabilitySource

logger = logging.getLogger("bella")

# Single owner of the seat-count staleness default: Settings.from_env's field
# default and CourseContent's fallback holder both derive from this constant
# instead of each hard-coding "24 hours".
DEFAULT_MAX_AGE_SECONDS = 24 * 60 * 60


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class SeatCountSnapshot:
    count: int
    fetched_at: datetime


class SeatCountHolder:
    """Holds the last successful count and omits it once it becomes stale."""

    def __init__(
        self,
        *,
        max_age: timedelta,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._max_age = max_age
        self._clock = clock
        self._snapshot: SeatCountSnapshot | None = None

    def update(self, count: int) -> None:
        if count < 0:
            raise ValueError("seat count cannot be negative")
        self._snapshot = SeatCountSnapshot(count, self._clock())

    def current_count(self) -> int | None:
        snapshot = self._snapshot
        if snapshot is None:
            return None
        if self._clock() - snapshot.fetched_at > self._max_age:
            return None
        return snapshot.count


class SeatCountRefresher:
    def __init__(
        self,
        source: AvailabilitySource,
        holder: SeatCountHolder,
        *,
        interval_seconds: int,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._source = source
        self._holder = holder
        self._interval_seconds = interval_seconds
        self._sleep = sleep

    async def refresh_once(self) -> bool:
        try:
            count = await self._source.fetch_count()
        except Exception as error:
            logger.warning(
                "seat count refresh failed: %s",
                str(error) or type(error).__name__,
            )
            return False
        self._holder.update(count)
        logger.info("seat count refreshed: %s seat(s)", count)
        return True

    async def run(self) -> None:
        while True:
            await self.refresh_once()
            await self._sleep(self._interval_seconds)

    async def close(self) -> None:
        await self._source.close()
