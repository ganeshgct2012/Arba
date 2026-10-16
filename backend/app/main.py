"""ArBa Promo Volume Planner - FastAPI application entry point.

Run from the project root:  python backend/app/main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    # Allow "python backend/app/main.py": make the "app" package importable.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncio
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import (
    APP_TITLE,
    FRONTEND_DIST,
    INBOUND_PROCESSED_DIR,
    INBOUND_QUEUE_DIR,
    OUTBOUND_DIR,
)
from app.db import create_schema_and_seed
from app.routers import (
    admin_users,
    auth,
    baseline,
    bootstrap,
    files,
    listing,
    pipelines,
    promotions,
    reports,
)
from app.services.scheduler import pipeline_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    for directory in (INBOUND_QUEUE_DIR, INBOUND_PROCESSED_DIR, OUTBOUND_DIR):
        directory.mkdir(parents=True, exist_ok=True)
    create_schema_and_seed()
    scheduler = asyncio.create_task(pipeline_scheduler())
    try:
        yield
    finally:
        scheduler.cancel()
        try:
            await scheduler
        except asyncio.CancelledError:
            pass


app = FastAPI(title=APP_TITLE, version="1.0.0", lifespan=lifespan)


app.include_router(auth.router)
app.include_router(bootstrap.router)
app.include_router(baseline.router)
app.include_router(promotions.router)
app.include_router(listing.router)
app.include_router(reports.router)
app.include_router(files.router)
app.include_router(admin_users.router)
app.include_router(pipelines.router)


app.mount(
    "/assets",
    StaticFiles(directory=FRONTEND_DIST / "assets", check_dir=False),
    name="frontend-assets",
)


@app.get("/", include_in_schema=False)
async def home() -> FileResponse:
    index_file = FRONTEND_DIST / "index.html"
    if not index_file.is_file():
        raise HTTPException(
            status_code=503,
            detail="React frontend is not built. Run `npm ci` and `npm run build` in frontend.",
        )
    return FileResponse(index_file)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    host = os.getenv("ARBA_HOST", "127.0.0.1")
    port = int(os.getenv("ARBA_PORT", "8171"))
    uvicorn.run(app, host=host, port=port)
