"""Shared singletons and auth dependency for the FastAPI application."""

import os
from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter

from podcast_maker.services.auth_provider import AuthProvider
from podcast_maker.services.podcast_repository import PodcastRepository
from podcast_maker.services.supabase.supabase_auth_provider import SupabaseAuthProvider
from podcast_maker.services.supabase.supabase_client import get_supabase_client
from podcast_maker.services.supabase.supabase_repository import SupabaseRepository
from podcast_maker.core.logging_config import get_logger

# ── Shared singletons ──────────────────────────────────────────────────────────
supabase_client = get_supabase_client()
repository: PodcastRepository = SupabaseRepository(supabase_client)
auth_provider: AuthProvider = SupabaseAuthProvider(
    supabase_url=os.environ["SUPABASE_URL"],
    jwt_secret=os.getenv("SUPABASE_JWT_SECRET"),
)


def get_repository() -> PodcastRepository:
    return repository


def get_auth_provider() -> AuthProvider:
    return auth_provider

# In-memory task store (not suitable for production – demo only)
tasks_status: dict = {}
logger = get_logger()


# ── Rate limiter ───────────────────────────────────────────────────────────────
def _global_key(request: Request) -> str:
    """Return the same key for every request (global rate limit)."""
    return "global"


limiter = Limiter(key_func=_global_key)


# ── Auth ───────────────────────────────────────────────────────────────────────
class AuthContext(BaseModel):
    user_id: str
    method: str = "supabase_jwt"


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
    auth_provider: AuthProvider = Depends(get_auth_provider),
    repository: PodcastRepository = Depends(get_repository),
) -> AuthContext:
    """Require a valid Supabase JWT Bearer token.

    Raises 401 if the token is absent, malformed, or fails verification.
    """
    if not authorization:
        logger.info("auth_failed reason=missing_authorization_header")
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not authorization.startswith("Bearer "):
        logger.info("auth_failed reason=invalid_authorization_scheme")
        raise HTTPException(status_code=401, detail="Unauthorized")

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        logger.info("auth_failed reason=empty_bearer_token")
        raise HTTPException(status_code=401, detail="Unauthorized")

    user = auth_provider.verify_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        repository.ensure_profile(user.user_id, user_name=user.display_name)
    except Exception as exc:
        logger.warning(
            "auth_profile_sync_failed user_id=%s error=%s",
            user.user_id,
            exc,
        )

    return AuthContext(user_id=user.user_id)
