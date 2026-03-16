from typing import Any, Dict, List, Optional

from postgrest.exceptions import APIError
from supabase import Client
from podcast_maker.core.logging_config import get_logger


logger = get_logger()


class RepositoryWriteError(RuntimeError):
    pass


class RepositoryPermissionError(RepositoryWriteError):
    pass


class SupabaseRepository:
    def __init__(self, client: Client):
        self.client = client

    def _normalize_user_name(self, user_name: Optional[str] = None) -> str:
        normalized = (user_name or "").strip()
        return normalized or "user"

    def _build_default_preferences(self) -> Dict[str, Any]:
        return {
            "preferred_hosts": ["sarah_curious", "mike_expert"],
        }

    def ensure_profile(self, user_id: str, user_name: Optional[str] = None) -> bool:
        payload: Dict[str, Any] = {
            "id": user_id,
            "user_name": self._normalize_user_name(user_name),
            "preferences": self._build_default_preferences(),
        }

        try:
            self.client.table("profiles").upsert(payload, on_conflict="id").execute()
            return True
        except Exception as exc:
            logger.warning("profiles_ensure_failed user_id=%s error=%s", user_id, exc)
            return False

    def upsert_user_preferences(self, user_id: str, preferred_hosts: List[str], user_name: Optional[str] = None) -> None:
        self.ensure_profile(user_id, user_name=user_name)
        payload = {
            "id": user_id,
            "user_name": self._normalize_user_name(user_name),
            "preferences": {
                "preferred_hosts": preferred_hosts,
            },
        }
        try:
            self.client.table("profiles").upsert(payload, on_conflict="id").execute()
        except APIError as exc:
            message = str(exc)
            if "row-level security policy" in message.lower():
                raise RepositoryPermissionError("profiles write blocked by row-level security") from exc
            raise RepositoryWriteError("failed to update user preferences") from exc

    def get_user_preferences(self, user_id: str) -> List[str]:
        response = (
            self.client.table("profiles")
            .select("preferences")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        data = getattr(response, "data", None)
        row = data if isinstance(data, dict) else None
        if not row:
            return self._build_default_preferences()["preferred_hosts"]

        preferences = row.get("preferences") if isinstance(row.get("preferences"), dict) else {}
        preferred_hosts = preferences.get("preferred_hosts") if isinstance(preferences, dict) else None
        if isinstance(preferred_hosts, list):
            return [str(host_id) for host_id in preferred_hosts]
        return self._build_default_preferences()["preferred_hosts"]

    def create_podcast_record(self, user_id: str, title: str, urls: Dict[str, str]) -> None:
        payload = {
            "title": title,
            "urls": urls,
            "user_id": user_id,
        }
        try:
            self.client.table("podcasts").insert(payload).execute()
        except APIError as exc:
            message = str(exc)
            if "row-level security policy" in message.lower():
                raise RepositoryPermissionError("podcasts write blocked by row-level security") from exc
            raise RepositoryWriteError("failed to create podcast record") from exc

    def get_user_podcasts(self, user_id: str) -> List[Dict[str, Any]]:
        response = (
            self.client.table("podcasts")
            .select("id, title, urls, user_id")
            .eq("user_id", user_id)
            .order("id", desc=True)
            .execute()
        )
        data = getattr(response, "data", None)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("profiles")
            .select("id, user_name, preferences")
            .eq("id", user_id)
            .maybe_single()
            .execute()
        )
        data = getattr(response, "data", None)
        if isinstance(data, dict):
            return data
        return None
