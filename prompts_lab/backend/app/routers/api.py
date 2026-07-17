"""
Router for Prompts Lab UI endpoints.
"""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
import yaml

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from engine.executor import PipelineExecutor
from engine.validator import validate_pipeline_data
import services.templates as templates

logger = logging.getLogger("prompts_lab_api")

router = APIRouter(prefix="/prompts-test-api", tags=["prompts-test-api"])

# Configuration paths
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
RESOURCES_ROOT = BACKEND_ROOT.parent / "common_resources"
PIPELINES_DIR = RESOURCES_ROOT / "templates"
RUNS_DIR = RESOURCES_ROOT / "experiments_runs"

LOCAL_USER_ID = "lab-local-user"

# Static Host configurations for Prompt Lab metadata
STATIC_HOSTS = json.load(RESOURCES_ROOT / "hosts.json")


# Models
class PipelineRunRequest(BaseModel):
    pipeline_yaml: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    run_stages: Optional[List[str]] = None
    mock_outputs: Dict[str, Any] = Field(default_factory=dict)


class PromptTemplateCreateRequest(BaseModel):
    stage: Literal["architect", "researcher", "outliner", "scriptwriter"]
    name: str = Field(min_length=1)
    prompt_text: str = Field(min_length=1)


class PromptTemplateUpdateRequest(BaseModel):
    name: Optional[str] = None
    prompt_text: Optional[str] = None


# Helpers
def _read_manifest(run_dir: Path) -> Optional[Dict[str, Any]]:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return None


# Endpoints
@router.get("/meta")
async def get_meta():
    """Retrieve metadata about host profiles and execution configurations."""
    return {
        "formats": ["dialogue", "solo"],
        "stages": ["architect", "researcher", "outliner", "scriptwriter"],
        "default_host_ids": ["sarah_curious", "mike_expert"],
        "hosts": STATIC_HOSTS,
        "default_runs_root": str(RUNS_DIR)
    }


# ============================================================================
# PIPELINES CRUD
# ============================================================================
@router.get("/pipelines")
async def list_pipelines():
    """List available pipeline configurations saved in experiments runs root."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    pipelines = []
    
    # Search for directories under RUNS_DIR
    for item in RUNS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            path = item / "pipeline.yaml"
            manifest_path = item / "run_manifest.json"
            
            # If pipeline.yaml is present, load metadata from it
            if path.is_file():
                try:
                    content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                    pipelines.append({
                        "id": item.name,
                        "name": content.get("name", item.name),
                        "description": content.get("description", ""),
                        "version": content.get("version", 1)
                    })
                except Exception:
                    pipelines.append({
                        "id": item.name,
                        "name": item.name,
                        "description": "Failed to parse YAML metadata",
                        "version": 1
                    })
            # Otherwise, if run_manifest.json is present, load metadata from manifest
            elif manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) or {}
                    pipelines.append({
                        "id": item.name,
                        "name": f"Run: {manifest.get('topic') or item.name}",
                        "description": f"Past execution run from {manifest.get('created_at_utc', 'unknown date')}",
                        "version": 1
                    })
                except Exception:
                    pipelines.append({
                        "id": item.name,
                        "name": item.name,
                        "description": "Historical execution run",
                        "version": 1
                    })
    # Sort by ID descending (same order as runs)
    pipelines.sort(key=lambda p: p["id"], reverse=True)
    return {"pipelines": pipelines}


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: str):
    """Retrieve the raw YAML content of a specific pipeline."""
    if "/" in pipeline_id or "\\" in pipeline_id or pipeline_id.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid pipeline ID")
    
    path = RUNS_DIR / pipeline_id / "pipeline.yaml"
    
    # If the file pipeline.yaml exists, return it directly
    if path.is_file():
        return Response(content=path.read_text(encoding="utf-8"), media_type="text/yaml")
        
    # If pipeline.yaml doesn't exist, check for run_manifest.json and prompt files to reconstruct it dynamically
    manifest_path = RUNS_DIR / pipeline_id / "run_manifest.json"
    if not manifest_path.is_file():
        raise HTTPException(status_code=404, detail="Pipeline not found")
        
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load run manifest: {exc}")
        
    # Reconstruct stages
    stages = []
    
    # Check each possible stage
    for stage_id in ["architect", "researcher", "outliner", "scriptwriter"]:
        prompt_file = RUNS_DIR / pipeline_id / f"prompt_{stage_id}.txt"
        if not prompt_file.is_file():
            continue
            
        try:
            prompt_text = prompt_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            prompt_text = f"Failed to load prompt snapshot for stage {stage_id}."
            
        stage_obj = {
            "id": stage_id,
            "type": "llm",
            "execution": "map" if stage_id == "researcher" else "single",
            "prompt": {
                "source": "inline",
                "text": prompt_text
            }
        }
        
        # Add map parameters for researcher
        if stage_id == "researcher":
            stage_obj["map"] = {
                "over": "architect.segments",
                "item_name": "segment"
            }
            stage_obj["response"] = {
                "kind": "text",
                "aggregate_file": "outputs/research.md",
                "aggregate_strategy": "concat_with_headers"
            }
            stage_obj["outputs"] = {
                "research": {
                    "source": "response.aggregate"
                }
            }
        elif stage_id == "architect":
            stage_obj["response"] = {
                "kind": "json",
                "file": "outputs/blueprint.json"
            }
            stage_obj["outputs"] = {
                "blueprint": {
                    "source": "response"
                },
                "segments": {
                    "source": "response.segments"
                }
            }
        elif stage_id == "outliner":
            stage_obj["response"] = {
                "kind": "json",
                "file": "outputs/outline.json"
            }
            stage_obj["outputs"] = {
                "outline": {
                    "source": "response"
                }
            }
        elif stage_id == "scriptwriter":
            stage_obj["response"] = {
                "kind": "text",
                "file": "outputs/script.txt"
            }
            stage_obj["outputs"] = {
                "script": {
                    "source": "response"
                }
            }
            
        stages.append(stage_obj)
        
    # Build complete pipeline object
    pipeline_obj = {
        "version": 1,
        "id": pipeline_id,
        "name": f"Reconstructed: {manifest.get('topic') or pipeline_id}",
        "description": f"Dynamically reconstructed pipeline from past run {pipeline_id}.",
        "inputs": {
            "topic": {
                "type": "text",
                "required": True
            }
        },
        "stages": stages
    }
    
    try:
        yaml_content = yaml.dump(pipeline_obj, allow_unicode=True, sort_keys=False)
        return Response(content=yaml_content, media_type="text/yaml")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate pipeline YAML: {exc}")


@router.post("/pipelines/{pipeline_id}")
async def save_pipeline(pipeline_id: str, request: Request):
    """Save raw YAML content for a pipeline."""
    if "/" in pipeline_id or "\\" in pipeline_id or pipeline_id.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid pipeline ID")
        
    body = await request.body()
    yaml_content = body.decode("utf-8")
    
    try:
        data = yaml.safe_load(yaml_content)
        # Fast semantic check
        validate_pipeline_data(data, BACKEND_ROOT)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline YAML: {exc}")
        
    pipeline_dir = RUNS_DIR / pipeline_id
    pipeline_dir.mkdir(parents=True, exist_ok=True)
    
    path = pipeline_dir / "pipeline.yaml"
    path.write_text(yaml_content, encoding="utf-8")
    
    return {"status": "saved", "id": pipeline_id}


@router.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: str):
    """Delete a pipeline directory."""
    if "/" in pipeline_id or "\\" in pipeline_id or pipeline_id.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid pipeline ID")
        
    pipeline_dir = RUNS_DIR / pipeline_id
    if not pipeline_dir.is_dir():
        raise HTTPException(status_code=404, detail="Pipeline not found")
        
    try:
        shutil.rmtree(pipeline_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete directory: {exc}")
        
    return {"status": "deleted", "id": pipeline_id}


@router.get("/pipeline-templates")
async def list_pipeline_templates():
    """List baseline templates for creating pipelines."""
    PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
    templates_list = []
    
    # Dynamically scan the templates directory instead of hard-coding template names
    for item in PIPELINES_DIR.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            path = item / "pipeline.yaml"
            if path.is_file():
                try:
                    yaml_content = path.read_text(encoding="utf-8")
                    content = yaml.safe_load(yaml_content) or {}
                    templates_list.append({
                        "id": item.name,
                        "name": content.get("name", item.name),
                        "description": content.get("description", ""),
                        "yaml": yaml_content
                    })
                except Exception:
                    pass
    # Sort templates by id
    templates_list.sort(key=lambda t: t["id"])
    return {"templates": templates_list}


# ============================================================================
# PIPELINE RUNNING
# ============================================================================
@router.post("/pipelines/run")
async def run_pipeline(payload: PipelineRunRequest):
    """Execute a pipeline configuration."""
    try:
        pipeline_data = yaml.safe_load(payload.pipeline_yaml)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}")

    try:
        validate_pipeline_data(pipeline_data, BACKEND_ROOT)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Pipeline validation failed: {exc}")

    try:
        executor = PipelineExecutor(
            pipeline_data=pipeline_data,
            inputs=payload.inputs,
            run_stages=payload.run_stages,
            mock_outputs=payload.mock_outputs,
            runs_root=RUNS_DIR,
            user_id=LOCAL_USER_ID
        )
        
        run_dir = executor.run()
        manifest = _read_manifest(run_dir) or {}
        
        # Populate stage outputs mapping to return to UI
        outputs = {}
        for record in manifest.get("stage_records", []):
            stage_id = record.get("stage")
            outputs[stage_id] = executor.stage_outputs.get(stage_id, {})
            
        return {
            "status": "completed",
            "run_id": run_dir.name,
            "outputs": outputs,
            "manifest": manifest
        }
    except Exception as exc:
        logger.error(f"Pipeline run failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ============================================================================
# RUN HISTORY
# ============================================================================
@router.get("/runs")
async def list_runs():
    """List past execution directories and manifest stats."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    runs = []
    
    for item in RUNS_DIR.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            manifest = _read_manifest(item)
            runs.append({
                "run_id": item.name,
                "run_directory": str(item),
                "has_manifest": manifest is not None,
                "topic": (manifest or {}).get("topic"),
                "stages": (manifest or {}).get("stages", []),
                "created_at_utc": (manifest or {}).get("created_at_utc")
            })
            
    # Sort by created_at_utc descending or folder name descending
    runs.sort(key=lambda r: r["run_id"], reverse=True)
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def get_run_details(run_id: str):
    """Retrieve detailed files list and manifest for a run."""
    if "/" in run_id or "\\" in run_id or run_id.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid run ID")
        
    run_dir = RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="Run directory not found")
        
    files = sorted([item.name for item in run_dir.iterdir() if item.is_file()])
    manifest = _read_manifest(run_dir)
    
    return {
        "run_id": run_id,
        "run_directory": str(run_dir),
        "files": files,
        "manifest": manifest
    }


@router.get("/runs/{run_id}/files/{file_name}")
async def get_run_file(run_id: str, file_name: str):
    """Retrieve raw file content from a past run."""
    if "/" in run_id or "\\" in run_id or run_id.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid run ID")
    if "/" in file_name or "\\" in file_name or file_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid file name")
        
    target = RUNS_DIR / run_id / file_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
        
    return {
        "run_id": run_id,
        "file_name": file_name,
        "content": target.read_text(encoding="utf-8", errors="replace")
    }


# ============================================================================
# STAGE PROMPT TEMPLATES CRUD
# ============================================================================
@router.get("/prompt-templates")
async def list_prompt_templates(stage: Optional[str] = None):
    """List all user stage prompt templates."""
    rows = templates.list_templates(LOCAL_USER_ID, stage)  # type: ignore
    return {"templates": rows}


@router.post("/prompt-templates")
async def create_prompt_template(payload: PromptTemplateCreateRequest):
    """Create a new prompt template."""
    template_id = str(uuid.uuid4())
    row = templates.create_template(
        user_id=LOCAL_USER_ID,
        template_id=template_id,
        stage=payload.stage,
        name=payload.name.strip(),
        prompt_text=payload.prompt_text.strip()
    )
    return row


@router.get("/prompt-templates/{template_id}")
async def get_prompt_template(template_id: str):
    """Retrieve a single prompt template."""
    if not templates.is_valid_template_id(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    try:
        return templates.get_template(LOCAL_USER_ID, template_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")


@router.put("/prompt-templates/{template_id}")
async def update_prompt_template(template_id: str, payload: PromptTemplateUpdateRequest):
    """Update a prompt template's name or text."""
    if not templates.is_valid_template_id(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    if payload.name is None and payload.prompt_text is None:
        raise HTTPException(status_code=400, detail="Provide name and/or prompt_text")
        
    name = payload.name.strip() if payload.name is not None else None
    prompt_text = payload.prompt_text.strip() if payload.prompt_text is not None else None
    
    try:
        return templates.update_template(
            user_id=LOCAL_USER_ID,
            template_id=template_id,
            name=name,
            prompt_text=prompt_text
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")


@router.delete("/prompt-templates/{template_id}")
async def delete_prompt_template(template_id: str):
    """Delete a prompt template."""
    if not templates.is_valid_template_id(template_id):
        raise HTTPException(status_code=400, detail="Invalid template ID")
    try:
        templates.delete_template(LOCAL_USER_ID, template_id)
        return {"status": "deleted", "id": template_id}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Template not found")
