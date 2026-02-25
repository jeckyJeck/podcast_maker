import uuid
from time import time
from typing import List, Optional
from dotenv import load_dotenv
import os
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse

from podcast_maker.core.orchestrator import PodcastMakerOrchestrator
from podcast_maker.core.paths import BACKEND_ROOT
from podcast_maker.core.logging_config import get_logger
from podcast_maker.services.google_cloud_storage_provider import GoogleCloudStorageProvider

load_dotenv(dotenv_path=BACKEND_ROOT / ".env")
BUCKET_NAME = os.getenv("BUCKET_NAME")
API_KEY = os.getenv("API_KEY")
app = FastAPI()
logger = get_logger()

# Initialize rate limiter - global limit (not per IP)
def get_global_key(request: Request) -> str:
    """Return same key for all requests (global limit)"""
    return "global"

limiter = Limiter(key_func=get_global_key)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda request, exc: JSONResponse(
    status_code=429,
    content={"detail": "Rate limit exceeded. Max 10 podcast creations per day (global limit)."}
))


# API Key verification dependency
async def verify_api_key(x_api_key: str = Header(...)) -> str:
    """Verify that the API key is valid"""
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key

# Allowed origins for CORS
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
]

tasks_status = {} # not suitable for production, just for demo purposes


@app.middleware("http")
async def handle_cors_and_logging(request: Request, call_next):
    origin = request.headers.get("origin")
    
    # Check if origin is allowed
    if origin in ALLOWED_ORIGINS:
        allowed_origin = origin
    else:
        allowed_origin = ALLOWED_ORIGINS[0]  # Default to first allowed origin
    
    # Handle CORS preflight requests
    if request.method == "OPTIONS":
        response = JSONResponse(content={}, status_code=200)
        response.headers["Access-Control-Allow-Origin"] = allowed_origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response
    
    start_time = time()
    logger.info(
        "api_request method=%s path=%s client=%s origin=%s",
        request.method,
        request.url.path,
        request.client.host if request.client else "unknown",
        origin,
    )
    response = await call_next(request)
    
    # Add CORS headers to all responses
    response.headers["Access-Control-Allow-Origin"] = allowed_origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-API-Key"
    
    duration_ms = int((time() - start_time) * 1000)
    logger.info(
        "api_response method=%s path=%s status=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# Request model for podcast creation
class PodcastRequest(BaseModel):
    topic: str
    host_ids: Optional[List[str]] = None  # Optional, will default to ["sarah_curious", "mike_expert"]


@app.post("/create-podcast/")
@limiter.limit("10/day")
async def create_podcast(
    request: Request,
    podcast_data: PodcastRequest,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(verify_api_key)
):
    task_id = str(uuid.uuid4())
    tasks_status[task_id] = {"status": "processing", "url": None}

    logger.info(
        "create_podcast task_id=%s topic=%s host_ids=%s",
        task_id,
        podcast_data.topic,
        podcast_data.host_ids,
    )
    
    # Validate host_ids if provided
    if podcast_data.host_ids:
        from podcast_maker.core.hosts_config import validate_host_selection
        try:
            validate_host_selection(podcast_data.host_ids)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    background_tasks.add_task(
        run_podcast_pipeline, 
        podcast_data.topic, 
        task_id, 
        podcast_data.host_ids
    )
    
    return {"task_id": task_id, "message": "Check status at /status/" + task_id}


def run_podcast_pipeline(topic: str, task_id: str, host_ids: Optional[List[str]] = None):
    try:
        storage = GoogleCloudStorageProvider(BUCKET_NAME)
        orchestrator = PodcastMakerOrchestrator(topic, storage, host_ids)
        final_url: dict = orchestrator.process_topic(topic)
        logger.info("pipeline_completed task_id=%s urls=%s", task_id, final_url)
        tasks_status[task_id] = {"status": "completed", "url": final_url}
    except Exception as e:
        logger.exception("pipeline_failed task_id=%s error=%s", task_id, e)
        tasks_status[task_id] = {"status": "failed", "error": str(e)}

@app.get("/status/{task_id}")
async def get_status(task_id: str, api_key: str = Depends(verify_api_key)):
    status = tasks_status.get(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@app.get("/available-hosts/")
async def get_available_hosts():
    """Get list of available hosts for podcast creation"""
    from podcast_maker.core.hosts_config import AVAILABLE_HOSTS
    
    hosts_list = []
    for host_id, profile in AVAILABLE_HOSTS.items():
        hosts_list.append({
            "id": profile.id,
            "name": profile.name,
            "tone": profile.tone,
            "role": profile.role,
            "gender": profile.gender,
            "personality": profile.personality
        })
    
    return {"hosts": hosts_list}