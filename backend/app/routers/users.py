"""Routes: current-user preferences and podcast history."""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies import AuthContext, get_current_user, repository
from podcast_maker.services.supabase.supabase_repository import RepositoryPermissionError, RepositoryWriteError

router = APIRouter(prefix="/me")


class UserPreferencesUpdateRequest(BaseModel):
    preferred_hosts: List[str]


@router.get("/preferences")
async def get_my_preferences(auth_context: AuthContext = Depends(get_current_user)):
    preferred_hosts = repository.get_user_preferences(auth_context.user_id)
    return {"preferred_hosts": preferred_hosts}


@router.put("/preferences")
async def update_my_preferences(
    payload: UserPreferencesUpdateRequest,
    auth_context: AuthContext = Depends(get_current_user),
):
    try:
        repository.upsert_user_preferences(auth_context.user_id, payload.preferred_hosts)
    except RepositoryPermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RepositoryWriteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"preferred_hosts": payload.preferred_hosts}


@router.get("/podcasts")
async def get_my_podcasts(auth_context: AuthContext = Depends(get_current_user)):
    records = repository.get_user_podcasts(auth_context.user_id)
    response: List[Dict[str, Any]] = []
    for record in records:
        urls = record.get("urls") if isinstance(record.get("urls"), dict) else None
        response.append(
            {
                "id": str(record.get("id")),
                "task_id": str(record.get("id")),
                "topic": record.get("title"),
                "host_ids": [],
                "status": "completed",
                "url": urls,
                "error": None,
                "created_at": None,
                "updated_at": None,
            }
        )
    return {"podcasts": response}
