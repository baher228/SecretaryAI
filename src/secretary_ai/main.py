from contextlib import asynccontextmanager

from fastapi import FastAPI

from secretary_ai.api.routes import router
from secretary_ai.core.config import get_settings
from secretary_ai.services.secretary import SecretaryService
from secretary_ai.ui.dashboard import router as dashboard_router


def create_app() -> FastAPI:
    settings = get_settings()

    secretary = SecretaryService(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await secretary.startup()
        try:
            yield
        finally:
            await secretary.shutdown()

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.secretary = secretary
    app.include_router(router, prefix="/api/v1")
    app.include_router(dashboard_router)
    return app


app = create_app()
