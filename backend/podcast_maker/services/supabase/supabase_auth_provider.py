from typing import Optional

import jwt
from jwt import PyJWKClient

from podcast_maker.core.logging_config import get_logger
from podcast_maker.services.auth_provider import AuthenticatedUser, AuthProvider

logger = get_logger()

_AUDIENCE = "authenticated"


class SupabaseAuthProvider(AuthProvider):
    """Verifies Supabase-issued JWTs locally — no network round-trip per request.

    Supabase signs access tokens either with a shared HS256 secret (legacy
    projects) or an asymmetric key exposed via a JWKS endpoint (current
    projects). Pass ``jwt_secret`` for the former; otherwise the JWKS endpoint
    is used, with keys fetched once and cached by PyJWKClient.
    """

    def __init__(self, supabase_url: str, jwt_secret: Optional[str] = None):
        self._issuer = f"{supabase_url}/auth/v1"
        self._jwt_secret = jwt_secret
        self._jwks_client: Optional[PyJWKClient] = (
            None
            if jwt_secret
            else PyJWKClient(f"{supabase_url}/auth/v1/.well-known/jwks.json")
        )

    def verify_token(self, token: str) -> Optional[AuthenticatedUser]:
        try:
            if self._jwt_secret:
                claims = jwt.decode(
                    token,
                    self._jwt_secret,
                    algorithms=["HS256"],
                    audience=_AUDIENCE,
                    issuer=self._issuer,
                )
            else:
                signing_key = self._jwks_client.get_signing_key_from_jwt(token)
                claims = jwt.decode(
                    token,
                    signing_key.key,
                    algorithms=["ES256", "RS256"],
                    audience=_AUDIENCE,
                    issuer=self._issuer,
                )
        except jwt.PyJWTError as exc:
            logger.info("auth_failed reason=jwt_verification_failed error=%s", exc)
            return None

        user_id = claims.get("sub")
        if not user_id:
            logger.info("auth_failed reason=missing_sub_claim")
            return None

        metadata = claims.get("user_metadata") or {}
        display_name = (
            metadata.get("name") or metadata.get("full_name") or metadata.get("user_name")
        )
        return AuthenticatedUser(user_id=user_id, display_name=display_name)
