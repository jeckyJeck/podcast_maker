from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class RepositoryWriteError(RuntimeError):
    pass


class RepositoryPermissionError(RepositoryWriteError):
    pass


class PodcastRepository(ABC):
    @abstractmethod
    def ensure_profile(self, user_id: str, user_name: Optional[str] = None) -> bool:
        """Create the user's profile if it doesn't exist yet."""

    @abstractmethod
    def upsert_user_preferences(
        self, user_id: str, preferred_hosts: List[str], user_name: Optional[str] = None
    ) -> None:
        """Persist the user's preferred hosts."""

    @abstractmethod
    def get_user_preferences(self, user_id: str) -> List[str]:
        """Return the user's preferred hosts, falling back to defaults if unset."""

    @abstractmethod
    def create_queued_podcast(self, user_id: str, task_id: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new podcast record in the 'queued' state."""

    @abstractmethod
    def get_podcast_by_task_id(self, user_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single podcast owned by the user by its task id."""

    @abstractmethod
    def get_podcast_by_id(self, user_id: str, podcast_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single podcast owned by the user by its id."""

    @abstractmethod
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
        """Update the status/checkpoint/urls/error of a podcast identified by task id."""

    @abstractmethod
    def get_user_podcasts(self, user_id: str) -> List[Dict[str, Any]]:
        """List all podcasts owned by the user, newest first."""

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
