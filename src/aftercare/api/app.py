from threading import Lock

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from aftercare import __version__
from aftercare.api.routes import router
from aftercare.config import PROJECT_ROOT, Settings
from aftercare.domain.contracts import BusinessError
from aftercare.repositories.database import database_health, session_factory
from aftercare.services.business import BusinessService


class LazyBusiness:
    """Health/import startup must remain usable even with unavailable or denied DB configuration."""

    def __init__(self, settings):
        self.settings = settings
        self.instance = None
        self.lock = Lock()

    def __getattr__(self, name):
        with self.lock:
            if self.instance is None:
                self.instance = BusinessService(session_factory(self.settings))
        return getattr(self.instance, name)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    app = FastAPI(title="售后 Agent 工作台", version=__version__)
    app.state.settings = config
    app.state.business = LazyBusiness(config)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"]
    )
    app.include_router(router)
    app.mount(
        "/static", StaticFiles(directory=PROJECT_ROOT / "src/aftercare/web/static"), name="static"
    )

    @app.get("/")
    def home():
        return FileResponse(PROJECT_ROOT / "src/aftercare/web/templates/index.html")

    @app.exception_handler(BusinessError)
    def business_error(request, error):
        return JSONResponse(
            status_code=404 if error.code == "NOT_FOUND" else 409,
            content={
                "ok": False,
                "error_code": error.code,
                "user_message": error.message,
                "retryable": error.retryable,
            },
        )

    @app.get("/health/live")
    def live() -> dict:
        return {
            "status": "alive",
            "phase": 4,
            "version": __version__,
            "mode": "offline",
            "demo_faults": config.dev_faults,
        }

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        health = database_health(config)
        return JSONResponse(
            status_code=200 if health.status == "ready" else 503,
            content={**health.model_dump(), "scope": "phase-4-infrastructure"},
        )

    return app
