"""Standalone backend entrypoint for prompts_lab experiments."""

from __future__ import annotations

from time import time
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.routers import prompts_test_api
from podcast_maker.core.logging_config import get_logger

# Load .env from lab_backend root directory
LAB_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=LAB_BACKEND_ROOT / ".env")

app = FastAPI(title="prompts_lab_backend")
logger = get_logger()

ALLOWED_ORIGINS = [
    "http://localhost:5180",
    "http://127.0.0.1:5180",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start_time = time()
    response = await call_next(request)
    duration_ms = int((time() - start_time) * 1000)
    logger.info(
        "lab_api_response method=%s path=%s status=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(prompts_test_api.router)
