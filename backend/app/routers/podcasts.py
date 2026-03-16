"""Routes: podcast creation and status polling."""

import uuid
from typing import List, Optional, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from app.dependencies import AuthContext, get_current_user, limiter, repository, tasks_status
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.orchestrator import PodcastMakerOrchestrator
from podcast_maker.core.prompt_manager import PodcastConfig
from podcast_maker.services.supabase.supabase_repository import RepositoryPermissionError, RepositoryWriteError
from podcast_maker.services.supabase.supabase_storage_provider import SupabaseStorageProvider

router = APIRouter()
logger = get_logger()


class PodcastRequest(BaseModel):
    topic: str
    host_ids: Optional[List[str]] = None  # defaults to ["sarah_curious", "mike_expert"]
    format: Optional[Literal["dialogue", "solo"]] = None


@router.post("/create-podcast/")
@limiter.limit("10/day")
async def create_podcast(
    request: Request,
    podcast_data: PodcastRequest,
    background_tasks: BackgroundTasks,
    auth_context: AuthContext = Depends(get_current_user),
):
    task_id = str(uuid.uuid4())
    resolved_host_ids = podcast_data.host_ids or ["sarah_curious", "mike_expert"]
    resolved_format = podcast_data.format

    if podcast_data.host_ids:
        from podcast_maker.core.hosts_config import validate_host_selection, get_host_profile
        try:
            if resolved_format == "solo":
                if len(podcast_data.host_ids) < 1:
                    raise ValueError("At least 1 host is required for solo format")
                for host_id in podcast_data.host_ids:
                    get_host_profile(host_id)
            else:
                validate_host_selection(podcast_data.host_ids)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    tasks_status[task_id] = {
        "status": "processing",
        "url": None,
        "user_id": auth_context.user_id,
        "topic": podcast_data.topic,
        "host_ids": resolved_host_ids,
        "format": resolved_format,
    }

    logger.info(
        "create_podcast task_id=%s topic=%s host_ids=%s format=%s user_id=%s",
        task_id,
        podcast_data.topic,
        resolved_host_ids,
        resolved_format,
        auth_context.user_id,
    )

    background_tasks.add_task(
        _run_podcast_pipeline,
        podcast_data.topic,
        task_id,
        resolved_host_ids,
        resolved_format,
        auth_context.user_id,
    )

    return {"task_id": task_id, "message": f"Check status at /status/{task_id}"}


@router.get("/status/{task_id}")
async def get_status(
    task_id: str,
    auth_context: AuthContext = Depends(get_current_user),
):
    status = tasks_status.get(task_id)
    if not status or status.get("user_id") != auth_context.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "status": status.get("status"),
        "url": status.get("url"),
        "error": status.get("error"),
    }


# ── Background worker ──────────────────────────────────────────────────────────

def _run_podcast_pipeline(
    topic: str,
    task_id: str,
    host_ids: List[str],
    podcast_format: Optional[str],
    user_id: str,
) -> None:
    try:
        path_prefix = f"{user_id}/{task_id}"
        storage = SupabaseStorageProvider(path_prefix=path_prefix)
        config = PodcastConfig(topic=topic, host_ids=host_ids, format=podcast_format)
        orchestrator = PodcastMakerOrchestrator(config, storage)

        final_url: dict = orchestrator.process_topic()
        logger.info("pipeline_completed task_id=%s urls=%s", task_id, final_url)
        tasks_status[task_id] = {"status": "completed", "url": final_url, "user_id": user_id}

        try:
            repository.create_podcast_record(user_id=user_id, title=topic, urls=final_url)
        except RepositoryPermissionError as exc:
            logger.warning("podcast_record_sync_failed task_id=%s reason=permission error=%s", task_id, exc)
        except RepositoryWriteError as exc:
            logger.warning("podcast_record_sync_failed task_id=%s reason=write_error error=%s", task_id, exc)
    except Exception as e:
        logger.exception("pipeline_failed task_id=%s error=%s", task_id, e)
        tasks_status[task_id] = {"status": "failed", "error": str(e), "user_id": user_id}
