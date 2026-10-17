from fastapi import FastAPI
from fastapi.responses import JSONResponse

from aftercare import __version__
from aftercare.config import Settings
from aftercare.repositories.database import database_health


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    app = FastAPI(title="售后 Agent 工作台", version=__version__)
    app.state.settings = config

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "alive", "phase": 1, "version": __version__, "mode": "offline"}

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        health = database_health(config)
        return JSONResponse(
            status_code=200 if health.status == "ready" else 503,
            content={**health.model_dump(), "scope": "phase-1-infrastructure"},
        )

    return app
