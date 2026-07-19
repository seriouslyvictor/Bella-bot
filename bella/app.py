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
from bella.seat_count import SeatCountRefresher

logger = logging.getLogger("bella")


def create_app(
    settings: Settings,
    pipeline: Pipeline,
    *,
    seat_count_refresher: SeatCountRefresher | None = None,
) -> FastAPI:
    """Wire the HTTP surface onto an already-built pipeline.

    Construction lives in bella.composition — see its docstring for why.
    """
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await pipeline.start()
        tasks = [asyncio.create_task(pipeline.run_retention())]
        if seat_count_refresher is not None:
            tasks.append(asyncio.create_task(seat_count_refresher.run()))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with suppress(asyncio.CancelledError):
                    await task
            if seat_count_refresher is not None:
                await seat_count_refresher.close()
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
        """Process liveness; does not make network calls."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        """Readiness to persist an inbound event and send its reply."""
        try:
            await pipeline.check_readiness()
        except Exception as error:
            # Log only the exception class: connection errors can include
            # operational details, and a health endpoint must never leak them.
            logger.warning("readiness check failed (%s)", type(error).__name__)
            raise HTTPException(
                status_code=503, detail="dependencies unavailable"
            ) from error
        return {"status": "ready"}

    @app.get("/assets/whatsapp-profile-picture.jpg")
    async def profile_picture() -> FileResponse:
        # Evolution GO's set-profile-picture call fetches this URL with a
        # plain HTTP GET (no header or JSON-body support), so it cannot carry
        # webhook credentials. Safe to leave open: internal-network-only, and
        # the only thing served is this one non-sensitive marketing asset.
        # JPEG because WhatsApp rejects PNG profile pictures.
        return FileResponse(settings.profile_picture_path, media_type="image/jpeg")

    @app.post("/webhook")
    async def webhook(request: Request, background: BackgroundTasks) -> dict[str, str]:
        try:
            payload: Any = await request.json()
        except Exception:
            payload = None

        # Evolution GO does not sign webhook deliveries, but it includes the
        # instance token at the top level. Authenticate it before parsing or
        # scheduling any message work; a non-string value is never a token.
        supplied_token = (
            payload.get("instanceToken") if isinstance(payload, dict) else None
        )
        candidate = supplied_token if isinstance(supplied_token, str) else ""
        token_matches = secrets.compare_digest(
            candidate.encode(), settings.evolution_api_key.encode()
        )
        if (
            not isinstance(supplied_token, str)
            or not settings.evolution_api_key
            or not token_matches
        ):
            raise HTTPException(status_code=403)

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

    from bella.composition import build_runtime

    logging.basicConfig(level=logging.INFO)
    settings = Settings.from_env()
    runtime = build_runtime(settings)
    app = create_app(
        settings,
        runtime.pipeline,
        seat_count_refresher=runtime.seat_count_refresher,
    )
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
