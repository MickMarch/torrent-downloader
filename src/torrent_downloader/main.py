"""Application entry point: FastAPI app factory and uvicorn launch helpers."""

import uvicorn
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from torrent_downloader.core.auth import verify_api_key
from torrent_downloader.core.config import config
from torrent_downloader.core.errors import AppException, ErrorCode
from torrent_downloader.core.limiter import limiter
from torrent_downloader.core.logger import app_logger
from torrent_downloader.core.middleware import RequestLoggingMiddleware
from torrent_downloader.routers import search, system, transfers

app: FastAPI = FastAPI(
    title="Torrent Downloader API",
    version="1.0.0",
    description=(
        "FastAPI microservice wrapping qBittorrent and TMDB. "
        "Exposes endpoints for media metadata search, torrent search, download submission, "
        "and disk usage reporting. Intended to be called by an orchestrating service "
        "such as a Discord bot or media library manager.\n\n"
        "All endpoints except `/api/v1/health` require an `X-API-Key` header. "
        "Rate limits: 60 req/min general, 20 req/min on search endpoints."
    ),
    contact={"name": "Michael Marchand", "url": "https://github.com/MickMarch/torrent_downloader"},
    openapi_tags=[
        {"name": "System", "description": "Health, storage, and cache management."},
        {"name": "Search", "description": "TMDB metadata lookup and torrent search."},
        {"name": "Transfers", "description": "Download submission and transfer management."},
    ],
)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after: int = exc.limit.limit.GRANULARITY.seconds
    response = JSONResponse(
        status_code=429,
        content={
            "status": "error",
            "code": ErrorCode.RATE_LIMITED.value,
            "detail": f"Rate limit exceeded. Retry after {retry_after} seconds.",
        },
    )
    response.headers["Retry-After"] = str(retry_after)
    return response

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "code": exc.code.value, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"status": "error", "code": ErrorCode.INVALID_INPUT.value, "detail": str(exc)},
    )

app.include_router(system.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])
app.include_router(transfers.router, prefix="/api/v1", dependencies=[Depends(verify_api_key)])


def custom_openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        contact=app.contact,
        tags=app.openapi_tags,
        routes=app.routes,
    )
    for path, methods in schema.get("paths", {}).items():
        for method, operation in methods.items():
            if path == "/api/v1/health":
                operation["security"] = []
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]


def main() -> None:
    """Start the production uvicorn server."""
    app_logger.info("Starting Torrent Downloader API Server...")
    uvicorn.run(
        "torrent_downloader.main:app", host=config.api_host, port=config.api_port
    )


def dev() -> None:
    """Start the uvicorn server with hot-reload enabled for local development."""
    app_logger.info("Starting Torrent Downloader API Server in DEV MODE...")
    uvicorn.run(
        "torrent_downloader.main:app",
        host=config.api_host,
        port=config.api_port,
        reload=True,
    )


if __name__ == "__main__":
    main()
