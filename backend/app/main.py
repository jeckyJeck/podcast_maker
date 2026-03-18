"""Application entry-point: thin app factory.

All auth logic lives in app.dependencies.
All route handlers live in app.routers.*
"""

from time import time

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.paths import BACKEND_ROOT
from app.dependencies import limiter
from app.routers import hosts, podcasts, users

load_dotenv(dotenv_path=BACKEND_ROOT / ".env")

app = FastAPI()
logger = get_logger()

# ── Rate limiter ───────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Max 10 podcast creations per day (global limit)."},
    ),
)

# ── CORS ───────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    # "http://localhost:5173",
    # "http://localhost:3000",
    # "http://127.0.0.1:5173",
    # "http://127.0.0.1:3000",
    "https://podcast-maker-nine.vercel.app/",
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
    origin = request.headers.get("origin")
    logger.info(
        "api_request method=%s path=%s client=%s origin=%s",
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
        origin,
    )
    response = await call_next(request)
    duration_ms = int((time() - start_time) * 1000)
    logger.info(
        "api_response method=%s path=%s status=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(podcasts.router)
app.include_router(users.router)
app.include_router(hosts.router)