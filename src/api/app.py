"""FastAPI Web Application Factory & Middleware Baseline for Telco Churn Platform.

Initializes FastAPI app, CORS middleware, slowapi rate limiting, non-PII structured
request logging middleware, and lifespan model initialization.
"""

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, cast

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.routes import router
from src.core.config import get_settings
from src.core.logging import get_logger
from src.inference.service import prediction_service

logger = get_logger(__name__)

# Initialize SlowAPI rate limiter
settings = get_settings()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_PER_MINUTE],
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup model loading and shutdown cleanup.

    CONSTRAINTS: Model loading failure at startup MUST fail loudly (process exits with
    a clear error), not serve silently with no model. If no Production-stage model
    exists in the registry at startup, this is also a hard failure.
    """
    logger.info("Executing FastAPI application startup lifespan...")
    try:
        prediction_service.load_production_model()
        logger.info(
            f"Startup complete: Production model version "
            f"{prediction_service.model_version} ready for inference."
        )
    except Exception as e:
        err_msg = (
            f"CRITICAL STARTUP FAILURE: Could not load Production model from MLflow "
            f"Registry. Process terminating loudly: {e}"
        )
        logger.error(err_msg)
        # Re-raise exception to force FastAPI / Uvicorn process exit
        raise RuntimeError(err_msg) from e

    yield

    logger.info("Executing FastAPI application shutdown cleanup...")


def create_app() -> FastAPI:
    """Construct and configure FastAPI application instance."""
    app_settings = get_settings()

    app = FastAPI(
        title="Telco Customer Churn Prediction API",
        description=(
            "Production-grade REST API serving registered MLflow Production model "
            "with feature pipeline transformation and decision thresholding."
        ),
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Attach Rate Limiter state & error handler
    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded, cast(Any, _rate_limit_exceeded_handler)
    )

    # CORS Middleware (Master Contract Section 11)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Structured Request Logging Middleware (NON-PII)
    @app.middleware("http")
    async def log_requests_middleware(request: Request, call_next: Any) -> Response:
        start_time = time.perf_counter()
        response: Response = await call_next(request)
        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

        client_host = request.client.host if request.client else "unknown"

        # Log metadata only — NO customer request body payload logged (NO PII)
        logger.info(
            "API HTTP Request processed",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "process_time_ms": process_time_ms,
                "client_host": client_host,
            },
        )
        response.headers["X-Process-Time-Ms"] = str(process_time_ms)
        return response

    # Global Exception Handler for Unhandled Errors
    @app.exception_handler(Exception)
    async def global_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.error(
            f"Unhandled exception during request processing: {exc}",
            extra={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An internal server error occurred."},
        )

    # Include API router endpoints
    app.include_router(router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.app:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=False,
    )
