"""Routes: current-user preferences and podcast history."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import AuthContext, get_current_user, get_repository
from podcast_maker.services.podcast_repository import PodcastRepository, RepositoryPermissionError, RepositoryWriteError

router = APIRouter(prefix="/me")


class UserPreferencesUpdateRequest(BaseModel):
    preferred_hosts: List[str]


@router.get("/preferences")
async def get_my_preferences(
    auth_context: AuthContext = Depends(get_current_user),
    repository: PodcastRepository = Depends(get_repository),
):
    preferred_hosts = repository.get_user_preferences(auth_context.user_id)
    return {"preferred_hosts": preferred_hosts}


@router.put("/preferences")
async def update_my_preferences(
    payload: UserPreferencesUpdateRequest,
    auth_context: AuthContext = Depends(get_current_user),
    repository: PodcastRepository = Depends(get_repository),
):
    try:
        repository.upsert_user_preferences(auth_context.user_id, payload.preferred_hosts)
    except RepositoryPermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RepositoryWriteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"preferred_hosts": payload.preferred_hosts}


@router.get("/podcasts")
async def get_my_podcasts(
    auth_context: AuthContext = Depends(get_current_user),
    repository: PodcastRepository = Depends(get_repository),
):
    records = repository.get_user_podcasts(auth_context.user_id)
    response: List[Dict[str, Any]] = []
    for record in records:
        urls = record.get("urls") if isinstance(record.get("urls"), dict) else {}
        config = record.get("config") if isinstance(record.get("config"), dict) else {}
        topic = config.get("topic") or record.get("title")
        host_ids = config.get("host_ids") if isinstance(config.get("host_ids"), list) else []
        response.append(
            {
                "id": str(record.get("id")),
                "task_id": str(record.get("task_id") or record.get("id")),
                "topic": topic,
                "host_ids": [str(host_id) for host_id in host_ids],
                "format": config.get("format") or "dialogue",
                "config": config,
                "status": record.get("status") or "completed",
                "checkpoint": record.get("checkpoint") or "completed",
                "url": urls or None,
                "error": record.get("error"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
            }
        )
    return {"podcasts": response}
