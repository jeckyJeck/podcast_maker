"""Shared singletons and auth dependency for the FastAPI application."""

from typing import Optional

from fastapi import Depends, Header, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter

from podcast_maker.services.supabase.supabase_client import get_supabase_client
from podcast_maker.services.supabase.supabase_repository import SupabaseRepository
from podcast_maker.core.logging_config import get_logger

# ── Shared singletons ──────────────────────────────────────────────────────────
supabase_client = get_supabase_client()
repository = SupabaseRepository(supabase_client)

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
) -> AuthContext:
    """Require a valid Supabase JWT Bearer token.

    Raises 401 if the token is absent, malformed, or rejected by Supabase.
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

    try:
        user_response = supabase_client.auth.get_user(token)
        user = getattr(user_response, "user", None)
        if user and getattr(user, "id", None):
            metadata = getattr(user, "user_metadata", None)
            user_name: Optional[str] = None
            if isinstance(metadata, dict):
                user_name = (
                    metadata.get("name")
                    or metadata.get("full_name")
                    or metadata.get("user_name")
                )
            try:
                repository.ensure_profile(user.id, user_name=user_name)
            except Exception as exc:
                logger.warning(
                    "auth_profile_sync_failed user_id=%s error=%s",
                    user.id,
                    exc,
                )
            return AuthContext(user_id=user.id)

        logger.info("auth_failed reason=supabase_user_missing")
    except Exception as exc:
        logger.warning("auth_failed reason=supabase_validation_exception error=%s", exc)

    raise HTTPException(status_code=401, detail="Unauthorized")
