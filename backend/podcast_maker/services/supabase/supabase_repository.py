from typing import Any, Dict, List, Optional

from postgrest.exceptions import APIError
from supabase import Client
from podcast_maker.core.logging_config import get_logger
from podcast_maker.services.retry import retry_network_call


logger = get_logger()


class RepositoryWriteError(RuntimeError):
    pass


class RepositoryPermissionError(RepositoryWriteError):
    pass


PODCAST_COLUMNS = "id, title, urls, user_id, task_id, status, checkpoint, config, error, created_at, updated_at"


class SupabaseRepository:
    def __init__(self, client: Client):
        self.client = client

    def _execute(self, operation: str, query):
        return retry_network_call(operation, query.execute)

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
            self._execute(
                "supabase.profiles.ensure",
                self.client.table("profiles").upsert(payload, on_conflict="id"),
            )
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
            self._execute(
                "supabase.profiles.upsert_preferences",
                self.client.table("profiles").upsert(payload, on_conflict="id"),
            )
        except APIError as exc:
            message = str(exc)
            if "row-level security policy" in message.lower():
                raise RepositoryPermissionError("profiles write blocked by row-level security") from exc
            raise RepositoryWriteError("failed to update user preferences") from exc

    def get_user_preferences(self, user_id: str) -> List[str]:
        response = self._execute(
            "supabase.profiles.get_preferences",
            self.client.table("profiles")
            .select("preferences")
            .eq("id", user_id)
            .maybe_single(),
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

    def _raise_write_error(self, exc: APIError, message: str) -> None:
        error_message = str(exc)
        if "row-level security policy" in error_message.lower():
            raise RepositoryPermissionError("podcasts write blocked by row-level security") from exc
        raise RepositoryWriteError(message) from exc

    def create_queued_podcast(
        self,
        user_id: str,
        task_id: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        topic = str(config.get("topic") or "Untitled Podcast")
        payload = {
            "title": topic,
            "urls": {},
            "user_id": user_id,
            "task_id": task_id,
            "status": "queued",
            "checkpoint": "requested",
            "config": config,
            "error": None,
        }
        try:
            response = self._execute(
                "supabase.podcasts.create_queued",
                self.client.table("podcasts").insert(payload),
            )
        except APIError as exc:
            self._raise_write_error(exc, "failed to create queued podcast")

        data = getattr(response, "data", None)
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return payload

    def create_podcast_record(self, user_id: str, title: str, urls: Dict[str, str]) -> None:
        payload = {
            "title": title,
            "urls": urls,
            "user_id": user_id,
            "status": "completed",
            "checkpoint": "completed",
        }
        try:
            self._execute(
                "supabase.podcasts.create_record",
                self.client.table("podcasts").insert(payload),
            )
        except APIError as exc:
            self._raise_write_error(exc, "failed to create podcast record")

    def get_podcast_by_task_id(self, user_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        response = self._execute(
            "supabase.podcasts.get_by_task_id",
            self.client.table("podcasts")
            .select(PODCAST_COLUMNS)
            .eq("user_id", user_id)
            .eq("task_id", task_id)
            .maybe_single(),
        )
        data = getattr(response, "data", None)
        if isinstance(data, dict):
            return data
        return None

    def get_podcast_by_id(self, user_id: str, podcast_id: str) -> Optional[Dict[str, Any]]:
        response = self._execute(
            "supabase.podcasts.get_by_id",
            self.client.table("podcasts")
            .select(PODCAST_COLUMNS)
            .eq("user_id", user_id)
            .eq("id", podcast_id)
            .maybe_single(),
        )
        data = getattr(response, "data", None)
        if isinstance(data, dict):
            return data
        return None

    def update_podcast_progress(
        self,
        user_id: str,
        task_id: str,
        *,
        status: Optional[str] = None,
        checkpoint: Optional[str] = None,
        urls: Optional[Dict[str, str]] = None,
        error: Optional[str] = None,
    ) -> None:
        payload: Dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if checkpoint is not None:
            payload["checkpoint"] = checkpoint
        if urls is not None:
            payload["urls"] = urls
        if error is not None or status in {"queued", "processing", "completed"}:
            payload["error"] = error
        if not payload:
            return

        try:
            self._execute(
                "supabase.podcasts.update_progress",
                self.client.table("podcasts").update(payload).eq("user_id", user_id).eq("task_id", task_id),
            )
        except APIError as exc:
            self._raise_write_error(exc, "failed to update podcast progress")

    def mark_podcast_failed(self, user_id: str, task_id: str, error: str) -> None:
        self.update_podcast_progress(user_id, task_id, status="failed", error=error)

    def mark_podcast_completed(self, user_id: str, task_id: str, urls: Dict[str, str]) -> None:
        self.update_podcast_progress(
            user_id,
            task_id,
            status="completed",
            checkpoint="completed",
            urls=urls,
            error=None,
        )

    def get_user_podcasts(self, user_id: str) -> List[Dict[str, Any]]:
        response = self._execute(
            "supabase.podcasts.get_user_podcasts",
            self.client.table("podcasts")
            .select(PODCAST_COLUMNS)
            .eq("user_id", user_id)
            .order("id", desc=True),
        )
        data = getattr(response, "data", None)
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    def get_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        response = self._execute(
            "supabase.profiles.get",
            self.client.table("profiles")
            .select("id, user_name, preferences")
            .eq("id", user_id)
            .maybe_single(),
        )
        data = getattr(response, "data", None)
        if isinstance(data, dict):
            return data
        return None
