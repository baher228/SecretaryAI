from fastapi import FastAPI

from secretary_ai.api.routes import router
from secretary_ai.core.config import get_settings
from secretary_ai.services.secretary import SecretaryService


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")
    app.state.secretary = SecretaryService(settings)
    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
