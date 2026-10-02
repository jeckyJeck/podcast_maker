"""Routes: podcast creation and status polling."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from app.dependencies import AuthContext, get_current_user, get_repository, limiter, tasks_status
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core import formats
from podcast_maker.core.podcast_job import PodcastConfig, PodcastJob
from podcast_maker.core.hosts_config import get_host_profile
from podcast_maker.services.podcast_repository import PodcastRepository, RepositoryPermissionError, RepositoryWriteError
from podcast_maker.services.supabase.supabase_storage_provider import SupabaseStorageProvider

router = APIRouter()
logger = get_logger()
STALE_PROCESSING_TIMEOUT = timedelta(minutes=15)


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None

    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_stale_processing(record: Dict[str, Any]) -> bool:
    if record.get("status") != "processing":
        return False

    updated_at = _parse_timestamp(record.get("updated_at"))
    if not updated_at:
        return False

    return datetime.now(timezone.utc) - updated_at > STALE_PROCESSING_TIMEOUT


class PodcastRequest(BaseModel):
    topic: str
    host_ids: Optional[List[str]] = None  # defaults to ["sarah_curious", "mike_expert"]
    format: Optional[str] = None  # a pipeline id (see GET /formats); default: the format written for len(host_ids) hosts
    inputs: Optional[Dict[str, Any]] = None  # extra values for inputs the pipeline declares beyond the platform ones


def _normalize_podcast_config(podcast_data: PodcastRequest) -> tuple[Dict[str, Any], str]:
    """Validate the request and freeze the plan: returns (config for the record, pipeline YAML text)."""
    topic = podcast_data.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="topic is required")

    host_ids = podcast_data.host_ids or ["sarah_curious", "mike_expert"]

    try:
        for host_id in host_ids:
            get_host_profile(host_id)
        format_id = podcast_data.format or formats.choose_format(len(host_ids))
        pipeline_text = formats.load_pipeline_text(format_id)
        pipeline_data = formats.parse_and_validate(pipeline_text)
        host_count = pipeline_data.get("host_count")
        if host_count is not None and len(host_ids) != host_count:
            raise ValueError(f"Format {format_id!r} requires exactly {host_count} host(s)")
        inputs = formats.build_inputs(pipeline_data, topic, host_ids, podcast_data.inputs)
    except ValueError as exc:  # includes formats.FormatError
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    config = {
        "topic": topic,
        "host_ids": host_ids,
        "format": format_id,
        "inputs": inputs,
        "stages": formats.stage_ids(pipeline_data),
    }
    return config, pipeline_text


def _podcast_status_response(record: Dict[str, Any]) -> Dict[str, Any]:
    urls = record.get("urls") if isinstance(record.get("urls"), dict) else {}
    return {
        "podcast_id": str(record.get("id")),
        "task_id": str(record.get("task_id") or record.get("id")),
        "status": record.get("status") or "completed",
        "checkpoint": record.get("checkpoint") or "completed",
        "url": urls or None,
        "stages": (record.get("config") or {}).get("stages") if isinstance(record.get("config"), dict) else None,
        "error": record.get("error"),
    }


def _save_pipeline_yaml(user_id: str, task_id: str, pipeline_text: str) -> str:
    storage = SupabaseStorageProvider(path_prefix=f"{user_id}/{task_id}")
    with tempfile.TemporaryDirectory(prefix="pipeline_") as tmp:
        path = Path(tmp) / "pipeline.yaml"
        path.write_text(pipeline_text, encoding="utf-8")
        return storage.save_file(str(path), "pipeline.yaml")


@router.get("/formats")
async def get_formats():
    """Public catalogue of podcast formats: one per pipeline YAML (id = pipeline id)."""
    return {"formats": formats.list_formats()}


@router.post("/create-podcast/")
@limiter.limit("10/day")
async def create_podcast(
    request: Request,
    podcast_data: PodcastRequest,
    background_tasks: BackgroundTasks,
    auth_context: AuthContext = Depends(get_current_user),
    repository: PodcastRepository = Depends(get_repository),
):
    task_id = str(uuid.uuid4())
    config, pipeline_text = _normalize_podcast_config(podcast_data)

    # First checkpoint: the exact pipeline YAML, saved with the episode's other files. Recovery reads this
    # copy (never the file on disk), so the stages and prompts of an episode can't change under it.
    try:
        pipeline_url = _save_pipeline_yaml(auth_context.user_id, task_id, pipeline_text)
    except Exception as exc:
        logger.exception("save_pipeline_failed task_id=%s", task_id)
        raise HTTPException(status_code=502, detail="failed to save the pipeline for this podcast") from exc

    try:
        podcast_record = repository.create_queued_podcast(
            user_id=auth_context.user_id,
            task_id=task_id,
            config=config,
            urls={formats.PIPELINE_URL_KEY: pipeline_url},
            checkpoint=formats.PIPELINE_URL_KEY,
        )
    except RepositoryPermissionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RepositoryWriteError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    tasks_status[task_id] = {
        "status": "queued",
        "url": {formats.PIPELINE_URL_KEY: pipeline_url},
        "user_id": auth_context.user_id,
        "checkpoint": formats.PIPELINE_URL_KEY,
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
        {formats.PIPELINE_URL_KEY: pipeline_url},
        repository,
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
    repository: PodcastRepository = Depends(get_repository),
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
    repository: PodcastRepository = Depends(get_repository),
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
    if (
        live_status
        and live_status.get("user_id") == auth_context.user_id
        and live_status.get("status") in {"queued", "processing"}
        and not _is_stale_processing(record)
    ):
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
        repository,
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
    existing_urls: Optional[Dict[str, str]],
    repository: PodcastRepository,
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
            host_ids=list(config_data.get("host_ids") or []),
            format=str(config_data.get("format") or ""),
            inputs=dict(config_data.get("inputs") or {}),
        )
        job = PodcastJob(config, storage, user_id=user_id)

        final_url: dict = job.run(
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
