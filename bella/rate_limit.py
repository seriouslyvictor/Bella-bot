"""Bounded per-number sliding-window rate limiting."""

from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto


@dataclass(frozen=True)
class RateLimitPolicy:
    max_messages: int = 10
    window_seconds: int = 60

    def __post_init__(self) -> None:
        if self.max_messages < 1 or self.window_seconds < 1:
            raise ValueError("rate limit values must be positive")


class RateLimitDecision(Enum):
    ALLOW = auto()
    NOTIFY = auto()
    SILENCE = auto()


@dataclass
class _RecipientState:
    events: deque[float]
    notified: bool = False


class SlidingWindowRateLimiter:
    """Tracks only the newest policy-sized event set for bounded memory use."""

    def __init__(
        self,
        policy: RateLimitPolicy,
        clock: Callable[[], float],
        recipient_capacity: int = 10_000,
    ) -> None:
        self._policy = policy
        self._clock = clock
        self._recipient_capacity = recipient_capacity
        self._states: OrderedDict[str, _RecipientState] = OrderedDict()

    def check(self, number: str) -> RateLimitDecision:
        now = self._clock()
        state = self._states.setdefault(
            number,
            _RecipientState(deque(maxlen=self._policy.max_messages)),
        )
        self._states.move_to_end(number)
        cutoff = now - self._policy.window_seconds
        while state.events and state.events[0] <= cutoff:
            state.events.popleft()

        allowed = len(state.events) < self._policy.max_messages
        already_notified = state.notified
        # Retain the newest attempts so a continuous flood extends the block,
        # while maxlen prevents one recipient from consuming unbounded RAM.
        state.events.append(now)
        state.notified = not allowed
        if allowed:
            decision = RateLimitDecision.ALLOW
        else:
            decision = (
                RateLimitDecision.SILENCE
                if already_notified
                else RateLimitDecision.NOTIFY
            )

        if len(self._states) > self._recipient_capacity:
            self._states.popitem(last=False)
        return decision
