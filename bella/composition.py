"""The production object graph.

Kept out of bella.app so that importing the app — which the tests do — never
pays for `import anthropic` (~2s) and never needs the SDK installed. Tests
build a Pipeline from fakes and hand it to create_app directly; this module is
imported only by the production entrypoint.
"""

from dataclasses import dataclass
from datetime import timedelta

from anthropic import AsyncAnthropic

from bella.availability import SenaiAvailabilitySource
from bella.anthropic_answerer import AnthropicAnswerer
from bella.anthropic_gate import AnthropicScopeGate
from bella.canned_replies import CannedReplies
from bella.config import Settings
from bella.conversation_store import PostgresConversationStore
from bella.course_content import CourseContent
from bella.evolution import EvolutionSender
from bella.pipeline import Pipeline
from bella.seat_count import SeatCountHolder, SeatCountRefresher


@dataclass(frozen=True)
class Runtime:
    pipeline: Pipeline
    seat_count_refresher: SeatCountRefresher


def build_runtime(settings: Settings) -> Runtime:
    """Read the content files and wire up every real collaborator, once."""
    holder = SeatCountHolder(
        max_age=timedelta(seconds=settings.seat_count_max_age_seconds)
    )
    content = CourseContent.from_files(
        settings.knowledge_base_path,
        settings.enrollment_card_path,
        seat_count_holder=holder,
    )
    # One client, one connection pool: the gate and the answerer both call
    # Anthropic back-to-back on every message. Their timeouts differ, which is
    # a per-request concern (see each module's TIMEOUT), not a per-client one.
    client = AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=1)
    pipeline = Pipeline(
        EvolutionSender(
            base_url=settings.evolution_url,
            api_key=settings.evolution_api_key,
            instance_id=settings.evolution_instance_id,
        ),
        AnthropicScopeGate(client),
        AnthropicAnswerer(client, content),
        CannedReplies.from_yaml(settings.canned_replies_path),
        content.enrollment_url,
        PostgresConversationStore(
            settings.database_url,
            required_database_name="bella",
        ),
        settings.apostila_path,
        content.human_contact_reply,
        settings.admin_contact,
        settings.rate_limit_policy,
        takeover_pause_seconds=settings.takeover_pause_seconds,
    )
    source = SenaiAvailabilitySource(content.senai_course_listing_url)
    refresher = SeatCountRefresher(
        source,
        holder,
        interval_seconds=settings.seat_count_refresh_seconds,
    )
    return Runtime(pipeline, refresher)
