"""Application entry point: FastAPI app factory and uvicorn launch helpers."""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from torrent_downloader.core.config import config
from torrent_downloader.core.logger import app_logger
from torrent_downloader.routers import search, system, transfers

app: FastAPI = FastAPI(title="Torrent Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(transfers.router, prefix="/api/v1")


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
