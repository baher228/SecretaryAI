import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from secretary_ai.api.routes import router
from secretary_ai.core.config import get_settings
from secretary_ai.services.secretary import SecretaryService
from secretary_ai.ui.dashboard import router as dashboard_router

logger = logging.getLogger(__name__)

# Configure root logger with structured format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def create_app() -> FastAPI:
    settings = get_settings()

    secretary = SecretaryService(settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info("Starting Secretary AI (model=%s, language=%s)", settings.openai_model, settings.language)
        await secretary.startup()
        logger.info("Secretary AI started successfully")
        try:
            yield
        finally:
            logger.info("Shutting down Secretary AI")
            await secretary.shutdown()
            logger.info("Secretary AI shut down")

    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.state.secretary = secretary
    app.include_router(router, prefix="/api/v1")
    app.include_router(dashboard_router)
    return app


app = create_app()
