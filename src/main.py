from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.app.api.v1.router import api_v1_router
from src.app.core.exceptions import AppException
from src.app.core.settings import get_settings
from src.app.middleware.request_id import RequestIDMiddleware
from src.app.observability.health import health_router
from src.app.observability.logging import configure_logging, get_logger
from src.modules.assets.infrastructure.scheduler import market_scheduler

settings = get_settings()
configure_logging(environment=settings.ENVIRONMENT, log_level=settings.LOG_LEVEL)
logger = get_logger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info(
        "Application startup",
        project=settings.PROJECT_NAME,
        environment=settings.ENVIRONMENT,
        debug=settings.DEBUG,
    )
    # Start periodic market price background task (~5 times a day, avoids per-user API limits)
    await market_scheduler.start()
    try:
        yield
    finally:
        await market_scheduler.stop()
        logger.info("Application shutdown")


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description="Personal Finance & Investment Management Platform API",
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
        openapi_url="/openapi.json" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Middleware
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handlers
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.warning(
            "Application exception handled",
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
                "message": exc.message,
                "code": exc.code,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = jsonable_encoder(exc.errors())
        logger.warning("Request validation failed", errors=errors)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "The submitted payload is invalid.",
                    "details": errors,
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please try again later.",
                }
            },
        )

    # Routers
    app.include_router(health_router)
    app.include_router(api_v1_router, prefix="/api/v1")

    # Root status and Favicon handler
    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            content={
                "name": settings.PROJECT_NAME,
                "version": "0.1.0",
                "status": "operational",
                "docs_url": "/docs",
                "api_v1": "/api/v1",
            }
        )

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


app = create_application()
