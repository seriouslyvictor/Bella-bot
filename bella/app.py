import asyncio
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse

from bella.config import Settings
from bella.evolution import parse_webhook
from bella.pipeline import Pipeline

logger = logging.getLogger("bella")


def create_app(settings: Settings, pipeline: Pipeline) -> FastAPI:
    """Wire the HTTP surface onto an already-built pipeline.

    Construction lives in bella.composition — see its docstring for why.
    """
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await pipeline.start()
        retention_task = asyncio.create_task(pipeline.run_retention())
        try:
            yield
        finally:
            retention_task.cancel()
            with suppress(asyncio.CancelledError):
                await retention_task
            await pipeline.close()

    app = FastAPI(
        title="Bella",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

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
    # Imported here, not at module scope: this is the one place that needs the
    # real object graph, and keeping it local is what lets the rest of this
    # module — the part tests import — stay free of the anthropic SDK.
    import uvicorn

    from bella.composition import build_pipeline

    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    app = create_app(settings, build_pipeline(settings))
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
