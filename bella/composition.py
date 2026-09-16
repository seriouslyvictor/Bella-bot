"""The production object graph for Nova."""

from dataclasses import dataclass

from google import genai

from bella.answer_guard import find_urls
from bella.app_registry import AppRegistry
from bella.canned_replies import CannedReplies
from bella.config import Settings
from bella.conversation_store import PostgresConversationStore
from bella.course_content import CourseContent
from bella.evolution import EvolutionSender
from bella.feedback_collector import FeedbackCollector
from bella.gemini_answerer import GeminiSupportAnswerer
from bella.gemini_gate import GeminiScopeGate
from bella.pipeline import Pipeline
from bella.reply_language import ReplyLanguage
from bella.response import policy_from_urls
from bella.triage_worker import GitHubIssuePublisher, TriageWorker


@dataclass(frozen=True)
class Runtime:
    pipeline: Pipeline
    triage_worker: TriageWorker


def build_runtime(settings: Settings) -> Runtime:
    enrollment_url = ""
    human_contact_reply = ""
    if (
        settings.enrollment_card_path.is_file()
        and settings.knowledge_base_path.is_file()
    ):
        content = CourseContent.from_files(
            settings.knowledge_base_path,
            settings.enrollment_card_path,
        )
        enrollment_url = content.enrollment_url
        human_contact_reply = content.human_contact_reply

    client = genai.Client(api_key=settings.gemini_api_key)
    scope_gate = GeminiScopeGate(client, model=settings.gemini_router_model)

    app_registry = AppRegistry.load_from_directory(settings.apps_dir)
    default_app = app_registry.default_app()

    support_answerer = GeminiSupportAnswerer(
        client,
        app_config=default_app,
        model=settings.gemini_agent_model,
    )

    conversation_store = PostgresConversationStore(
        settings.database_url,
        required_database_name="bella",
    )

    feedback_collector = FeedbackCollector(
        client=client,
        app_id=default_app.app_id,
        app_name=default_app.name,
        model=settings.gemini_agent_model,
        inbox_path=settings.inbox_path,
    )

    publisher = GitHubIssuePublisher(token=settings.github_token)
    triage_worker = TriageWorker(
        store=conversation_store,
        publisher=publisher,
        app_registry=app_registry,
    )

    canned = CannedReplies.from_yaml(settings.canned_replies_path)

    # A deployment without an Enrollment Card (every Nova deployment) has no
    # contact from content, so the configured one is the source of truth. An
    # unset contact is fine: the handoff branch says a human was notified
    # instead of sending nothing.
    if not human_contact_reply:
        human_contact_reply = settings.human_contact_reply

    # The reply contract: what may be linked, how long a message may be, and
    # what a reply degrades to when a branch produces nothing.
    response_policy = policy_from_urls(
        canned.error_reply,
        (
            *settings.allowed_reply_urls,
            enrollment_url,
            *find_urls(human_contact_reply),
        ),
        translations={
            language.value: canned.reply("error_reply", language)
            for language in ReplyLanguage
        },
    )

    pipeline = Pipeline(
        EvolutionSender(
            base_url=settings.evolution_url,
            api_key=settings.evolution_api_key,
            instance_id=settings.evolution_instance_id,
        ),
        scope_gate,
        support_answerer,
        canned,
        enrollment_url,
        conversation_store,
        settings.apostila_path,
        human_contact_reply,
        settings.admin_contact,
        settings.rate_limit_policy,
        takeover_pause_seconds=settings.takeover_pause_seconds,
        feedback_collector=feedback_collector,
        support_answerer=support_answerer,
        triage_worker=triage_worker,
        response_policy=response_policy,
    )
    return Runtime(pipeline=pipeline, triage_worker=triage_worker)
