"""
Main entrypoint for Prompts Lab FastAPI application.
"""

from __future__ import annotations

import logging
from pathlib import Path
from time import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load .env file from backend root
BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BACKEND_ROOT / ".env")

from app.routers import api

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("prompts_lab")

app = FastAPI(title="prompts_lab_backend", version="1.0.0")

# CORS configurations matching UI client development environments
ALLOWED_ORIGINS = [
    "http://localhost:5180",
    "http://127.0.0.1:5180",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
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
        "lab_api_call method=%s path=%s status=%s duration=%dms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms
    )
    return response


@app.get("/health")
async def health():
    return {"status": "ok"}


app.include_router(api.router)
