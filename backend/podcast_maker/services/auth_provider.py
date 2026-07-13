from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class AuthenticatedUser(BaseModel):
    user_id: str
    display_name: Optional[str] = None


class AuthProvider(ABC):
    @abstractmethod
    def verify_token(self, token: str) -> Optional[AuthenticatedUser]:
        """Validate a bearer token and return the authenticated identity, or None if invalid."""
