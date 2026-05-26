"""Routes: podcast creation and status polling."""

import uuid
from typing import Any, Dict, List, Optional, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from app.dependencies import AuthContext, get_current_user, limiter, repository, tasks_status
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.orchestrator import PodcastMakerOrchestrator
from podcast_maker.core.prompt_manager import PodcastConfig
from podcast_maker.core.hosts_config import validate_host_selection, get_host_profile
from podcast_maker.services.supabase.supabase_repository import RepositoryPermissionError, RepositoryWriteError
from podcast_maker.services.supabase.supabase_storage_provider import SupabaseStorageProvider

router = APIRouter()
logger = get_logger()


class PodcastRequest(BaseModel):
    topic: str
    host_ids: Optional[List[str]] = None  # defaults to ["sarah_curious", "mike_expert"]
    format: Optional[Literal["dialogue", "solo"]] = None


def _normalize_podcast_config(podcast_data: PodcastRequest) -> Dict[str, Any]:
    topic = podcast_data.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    host_ids = podcast_data.host_ids or ["sarah_curious", "mike_expert"]
    podcast_format = podcast_data.format or ("solo" if len(host_ids) == 1 else "dialogue")

    try:
        if podcast_format == "solo":
            if len(host_ids) != 1:
                raise ValueError("Solo format requires exactly 1 host")
            get_host_profile(host_ids[0])
        else:
            validate_host_selection(host_ids)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "topic": topic,
        "host_ids": host_ids,
        "format": podcast_format,
    }


def _podcast_status_response(record: Dict[str, Any]) -> Dict[str, Any]:
    urls = record.get("urls") if isinstance(record.get("urls"), dict) else {}
    return {
        "podcast_id": str(record.get("id")),
        "task_id": str(record.get("task_id") or record.get("id")),
        "status": record.get("status") or "completed",
        "checkpoint": record.get("checkpoint") or "completed",
        "url": urls or None,
        "error": record.get("error"),
    }


@router.post("/create-podcast/")
@limiter.limit("10/day")
async def create_podcast(
    request: Request,
    podcast_data: PodcastRequest,
    background_tasks: BackgroundTasks,
    auth_context: AuthContext = Depends(get_current_user),
):
    task_id = str(uuid.uuid4())
    config = _normalize_podcast_config(podcast_data)

    try:
        podcast_record = repository.create_queued_podcast(
            user_id=auth_context.user_id,
            task_id=task_id,
            config=config,
        )
    except RepositoryPermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RepositoryWriteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    tasks_status[task_id] = {
        "status": "queued",
        "url": None,
        "user_id": auth_context.user_id,
        "checkpoint": "requested",
        "podcast_id": str(podcast_record.get("id")),
        "config": config,
    }

    logger.info(
        "create_podcast task_id=%s topic=%s host_ids=%s format=%s user_id=%s",
        task_id,
        config["topic"],
        config["host_ids"],
        config["format"],
        auth_context.user_id,
    )

    background_tasks.add_task(
        _run_podcast_pipeline,
        task_id,
        auth_context.user_id,
        config,
        {},
    )

    return {
        "podcast_id": str(podcast_record.get("id")),
        "task_id": task_id,
        "message": f"Check status at /status/{task_id}",
    }


@router.get("/status/{task_id}")
async def get_status(
    task_id: str,
    auth_context: AuthContext = Depends(get_current_user),
):
    record = repository.get_podcast_by_task_id(auth_context.user_id, task_id)
    if record:
        return _podcast_status_response(record)

    status = tasks_status.get(task_id)
    if not status or status.get("user_id") != auth_context.user_id:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task_id,
        "podcast_id": status.get("podcast_id"),
        "status": status.get("status"),
        "checkpoint": status.get("checkpoint"),
        "url": status.get("url"),
        "error": status.get("error"),
    }


@router.post("/podcasts/{podcast_id}/retry")
async def retry_podcast(
    podcast_id: str,
    background_tasks: BackgroundTasks,
    auth_context: AuthContext = Depends(get_current_user),
):
    record = repository.get_podcast_by_id(auth_context.user_id, podcast_id)
    if not record:
        raise HTTPException(status_code=404, detail="Podcast not found")
    if record.get("status") == "completed":
        raise HTTPException(status_code=400, detail="Completed podcasts cannot be retried")

    config = record.get("config") if isinstance(record.get("config"), dict) else {}
    urls = record.get("urls") if isinstance(record.get("urls"), dict) else {}
    task_id = str(record.get("task_id") or uuid.uuid4())

    if not config.get("topic"):
        raise HTTPException(status_code=400, detail="Podcast config is missing")

    live_status = tasks_status.get(task_id)
    if live_status and live_status.get("user_id") == auth_context.user_id and live_status.get("status") in {"queued", "processing"}:
        return {
            "podcast_id": podcast_id,
            "task_id": task_id,
            "message": f"Already running. Check status at /status/{task_id}",
        }

    repository.update_podcast_progress(
        auth_context.user_id,
        task_id,
        status="queued",
        error=None,
    )
    tasks_status[task_id] = {
        "status": "queued",
        "url": urls or None,
        "user_id": auth_context.user_id,
        "checkpoint": record.get("checkpoint") or "requested",
        "podcast_id": podcast_id,
        "config": config,
    }

    background_tasks.add_task(
        _run_podcast_pipeline,
        task_id,
        auth_context.user_id,
        config,
        urls,
    )

    return {
        "podcast_id": podcast_id,
        "task_id": task_id,
        "message": f"Check status at /status/{task_id}",
    }


# Background worker

def _run_podcast_pipeline(
    task_id: str,
    user_id: str,
    config_data: Dict[str, Any],
    existing_urls: Optional[Dict[str, str]] = None,
) -> None:
    urls = dict(existing_urls or {})

    def progress(checkpoint: str, next_urls: Dict[str, str]) -> None:
        urls.clear()
        urls.update(next_urls)
        tasks_status[task_id] = {
            "status": "processing",
            "url": dict(urls) or None,
            "user_id": user_id,
            "checkpoint": checkpoint,
        }
        repository.update_podcast_progress(
            user_id,
            task_id,
            status="processing",
            checkpoint=checkpoint,
            urls=dict(urls),
            error=None,
        )

    try:
        repository.update_podcast_progress(user_id, task_id, status="processing", error=None)
        path_prefix = f"{user_id}/{task_id}"
        storage = SupabaseStorageProvider(path_prefix=path_prefix)
        config = PodcastConfig(
            topic=str(config_data.get("topic") or ""),
            host_ids=list(config_data.get("host_ids") or ["sarah_curious", "mike_expert"]),
            format=str(config_data.get("format") or "dialogue"),
        )
        orchestrator = PodcastMakerOrchestrator(config, storage)

        final_url: dict = orchestrator.process_topic(
            existing_urls=urls,
            progress_callback=progress,
        )
        logger.info("pipeline_completed task_id=%s urls=%s", task_id, final_url)
        tasks_status[task_id] = {
            "status": "completed",
            "url": final_url,
            "user_id": user_id,
            "checkpoint": "completed",
        }
        repository.mark_podcast_completed(user_id, task_id, final_url)
    except Exception as e:
        logger.exception("pipeline_failed task_id=%s error=%s", task_id, e)
        tasks_status[task_id] = {
            "status": "failed",
            "error": str(e),
            "user_id": user_id,
            "url": dict(urls) or None,
        }
        try:
            repository.mark_podcast_failed(user_id, task_id, str(e))
        except RepositoryWriteError as exc:
            logger.warning("podcast_record_failure_sync_failed task_id=%s error=%s", task_id, exc)
