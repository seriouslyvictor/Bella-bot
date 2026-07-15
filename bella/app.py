import logging
import secrets
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from bella.config import Settings
from bella.canned_replies import CannedReplies
from bella.evolution import EvolutionSender, WhatsAppSender, parse_webhook
from bella.pipeline import Answerer, Pipeline, PlaceholderAnswerer
from bella.scope_gate import ScopeGate

logger = logging.getLogger("bella")


def create_app(
    settings: Settings,
    sender: WhatsAppSender | None = None,
    scope_gate: ScopeGate | None = None,
    answerer: Answerer | None = None,
) -> FastAPI:
    if sender is None:
        sender = EvolutionSender(
            base_url=settings.evolution_url,
            api_key=settings.evolution_api_key,
            instance_id=settings.evolution_instance_id,
        )
    if scope_gate is None:
        from bella.anthropic_gate import AnthropicScopeGate

        scope_gate = AnthropicScopeGate(api_key=settings.anthropic_api_key)
    pipeline = Pipeline(
        sender,
        scope_gate,
        answerer or PlaceholderAnswerer(),
        CannedReplies.from_yaml(settings.canned_replies_path),
    )
    app = FastAPI(title="Bella", docs_url=None, redoc_url=None, openapi_url=None)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/assets/whatsapp-profile-picture.png")
    async def profile_picture() -> FileResponse:
        # Evolution GO's set-profile-picture call fetches this URL with a
        # plain HTTP GET (no header support), so it cannot carry the webhook
        # secret. Safe to leave open: internal-network-only, and the only
        # thing served is this one non-sensitive marketing asset.
        return FileResponse(settings.profile_picture_path, media_type="image/png")

    @app.post("/webhook/{secret}")
    async def webhook(
        secret: str, request: Request, background: BackgroundTasks
    ) -> dict[str, str]:
        # Evolution GO has no webhook signing; the secret lives in the URL we
        # register on the instance. Constant-time compare, reject outsiders.
        if not secrets.compare_digest(secret, settings.webhook_secret):
            raise HTTPException(status_code=403)

        try:
            payload: Any = await request.json()
        except Exception:
            payload = None

        message = parse_webhook(payload)
        if message is not None:
            # Ack fast: Evolution retries after 30s without a 2xx. Real work
            # happens after the response goes out.
            background.add_task(pipeline.handle, message)
        return {"status": "ok"}

    return app


def main() -> None:
    """Entrypoint for production: uvicorn bella.app:main-created app."""
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    app = create_app(Settings.from_env())
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
