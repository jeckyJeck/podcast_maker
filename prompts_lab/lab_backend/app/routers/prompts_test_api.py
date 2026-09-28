"""Routes: isolated prompts_test API for UI-driven prompt lab workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import uuid
from pathlib import Path
from typing import Any, Literal, Mapping

from fastapi import APIRouter, Body, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.hosts_config import AVAILABLE_HOSTS
from utils.paths import BACKEND_ROOT
from services import prompt_template_store
from prompts_test.compare import compare_files, list_run_directories, resolve_run_dir

router = APIRouter(prefix="/prompts-test-api", tags=["prompts-test-api"])

LOCAL_USER_ID = "lab-local-user"


class CompareRequest(BaseModel):
    run_a: str
    run_b: str
    file_name: str = "research.md"
    max_lines: int = 200
    runs_root: str | None = None


class PromptTemplateCreateRequest(BaseModel):
    stage: Literal["architect", "researcher", "outliner", "scriptwriter"]
    name: str = Field(min_length=1)
    prompt_text: str = Field(min_length=1)


class PromptTemplateUpdateRequest(BaseModel):
    name: str | None = None
    prompt_text: str | None = None


class PromptTemplateResponse(BaseModel):
    id: str
    user_id: str
    stage: Literal["architect", "researcher", "outliner", "scriptwriter"]
    name: str
    prompt_text: str
    created_at_utc: str
    updated_at_utc: str


@dataclass
class AuthContext:
    user_id: str
    method: str = "disabled"


def _sanitize_template_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{field_name} cannot be empty")
    return cleaned


def _validate_template_id(template_id: str) -> str:
    if not prompt_template_store.is_valid_template_id(template_id):
        raise HTTPException(status_code=400, detail="Invalid template id")
    return template_id


def _to_template_response(row: Mapping[str, Any]) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=str(row.get("id", "")),
        user_id=str(row.get("user_id", "")),
        stage=row.get("stage", "architect"),
        name=str(row.get("name", "")),
        prompt_text=str(row.get("prompt_text", "")),
        created_at_utc=str(row.get("created_at_utc", "")),
        updated_at_utc=str(row.get("updated_at_utc", "")),
    )


async def get_prompts_test_auth() -> AuthContext:
    """Return a fixed local auth context for the isolated prompts lab backend."""
    return AuthContext(user_id=LOCAL_USER_ID)


def _default_runs_root() -> Path:
    return BACKEND_ROOT.parent / "common_resources" / "experiments_runs"


def _default_fixtures_root() -> Path:
    return BACKEND_ROOT / "prompts_test" / "fixtures"


def _resolve_runs_root(runs_root: str | None) -> Path:
    return Path(runs_root) if runs_root else _default_runs_root()


def _read_manifest(run_dir: Path) -> dict | None:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


@router.get("/meta")
async def prompts_test_meta(_auth: AuthContext = Depends(get_prompts_test_auth)):
    hosts = [
        {
            "id": profile.id,
            "name": profile.name,
            "tone": profile.tone,
            "role": profile.role,
            "gender": profile.gender,
        }
        for profile in AVAILABLE_HOSTS.values()
    ]

    return {
        "formats": ["dialogue", "solo"],
        "default_host_ids": ["sarah_curious", "mike_expert"],
        "hosts": hosts,
        "default_runs_root": str(_default_runs_root()),
    }


@router.get("/runs")
async def prompts_test_list_runs(
    runs_root: str | None = None,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    root = _resolve_runs_root(runs_root)
    runs = []
    for run_dir in list_run_directories(root):
        manifest = _read_manifest(run_dir)
        runs.append(
            {
                "run_id": run_dir.name,
                "run_directory": str(run_dir),
                "has_manifest": manifest is not None,
                "topic": (manifest or {}).get("inputs", {}).get("topic"),
                "stages": (manifest or {}).get("run_stages", []),
                "created_at_utc": (manifest or {}).get("started_at_utc"),
            }
        )
    return {"runs": runs}


@router.get("/runs/{run_id}")
async def prompts_test_run_details(
    run_id: str,
    runs_root: str | None = None,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    root = _resolve_runs_root(runs_root)
    run_dir = resolve_run_dir(root, run_id)
    files = sorted([item.name for item in run_dir.iterdir() if item.is_file()])
    manifest = _read_manifest(run_dir)
    return {
        "run_id": run_dir.name,
        "run_directory": str(run_dir),
        "files": files,
        "manifest": manifest,
    }


def _resolve_run_file(run_dir: Path, file_name: str) -> Path:
    # Stage response files are pipeline-defined and may live under subdirectories
    # (e.g. "outputs/blueprint.json"), so nested paths are allowed here. What's not
    # allowed is escaping run_dir: no ".." segments, and the resolved path must stay
    # inside run_dir.
    if any(part in ("..", "") for part in Path(file_name).parts) or file_name.startswith((".", "/", "\\")):
        raise HTTPException(status_code=400, detail=f"Invalid file name: {file_name}")

    target = (run_dir / file_name).resolve()
    if run_dir.resolve() not in target.parents:
        raise HTTPException(status_code=400, detail=f"Invalid file name: {file_name}")
    return target


@router.get("/runs/{run_id}/files/{file_name:path}")
async def prompts_test_run_file(
    run_id: str,
    file_name: str,
    runs_root: str | None = None,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    root = _resolve_runs_root(runs_root)
    run_dir = resolve_run_dir(root, run_id)
    target = _resolve_run_file(run_dir, file_name)

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return {
        "run_id": run_dir.name,
        "file_name": file_name,
        "content": target.read_text(encoding="utf-8", errors="replace"),
    }


class EvaluateRunRequest(BaseModel):
    content_files: dict[str, str] = Field(min_length=1)
    rubric_id: str = "podcast_quality"
    context_files: dict[str, str] | None = None


@router.get("/eval-rubrics")
async def list_eval_rubrics(_auth: AuthContext = Depends(get_prompts_test_auth)):
    from evaluation.rubric import list_rubrics

    return {"rubrics": list_rubrics()}


@router.post("/runs/{run_id}/evaluate")
async def prompts_test_evaluate_run(
    run_id: str,
    payload: EvaluateRunRequest,
    runs_root: str | None = None,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    root = _resolve_runs_root(runs_root)
    run_dir = resolve_run_dir(root, run_id)

    # Validate every referenced path stays inside run_dir before touching the evaluator.
    for rel_path in list(payload.content_files.values()) + list((payload.context_files or {}).values()):
        _resolve_run_file(run_dir, rel_path)

    from evaluation.evaluator import EvaluationError, evaluate_run

    try:
        result = evaluate_run(
            run_dir,
            content_files=payload.content_files,
            rubric_id=payload.rubric_id,
            context_files=payload.context_files,
        )
    except EvaluationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"run_id": run_dir.name, "evaluation": result.to_dict()}


@router.get("/runs/{run_id}/evaluation")
async def prompts_test_get_evaluation(
    run_id: str,
    runs_root: str | None = None,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    root = _resolve_runs_root(runs_root)
    run_dir = resolve_run_dir(root, run_id)
    eval_path = run_dir / "evaluation.json"
    if not eval_path.exists():
        raise HTTPException(status_code=404, detail="Run has not been evaluated")
    return {"run_id": run_dir.name, "evaluation": json.loads(eval_path.read_text(encoding="utf-8"))}


@router.post("/compare")
async def prompts_test_compare(
    payload: CompareRequest,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    try:
        root = _resolve_runs_root(payload.runs_root)
        run_a = resolve_run_dir(root, payload.run_a)
        run_b = resolve_run_dir(root, payload.run_b)
        diff = compare_files(run_a, run_b, payload.file_name, max_lines=payload.max_lines)
        return {
            "run_a": run_a.name,
            "run_b": run_b.name,
            "file_name": payload.file_name,
            "diff": diff,
        }
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/prompt-templates")
async def prompts_test_list_prompt_templates(
    stage: Literal["architect", "researcher", "outliner", "scriptwriter"] | None = None,
    auth: AuthContext = Depends(get_prompts_test_auth),
):
    rows = prompt_template_store.list_templates(auth.user_id, stage)
    return {"templates": [_to_template_response(row).model_dump() for row in rows]}


@router.post("/prompt-templates")
async def prompts_test_create_prompt_template(
    payload: PromptTemplateCreateRequest,
    auth: AuthContext = Depends(get_prompts_test_auth),
):
    name = _sanitize_template_text(payload.name, "name")
    prompt_text = _sanitize_template_text(payload.prompt_text, "prompt_text")
    template_id = str(uuid.uuid4())
    row = prompt_template_store.create_template(
        user_id=auth.user_id,
        template_id=template_id,
        stage=payload.stage,
        name=name,
        prompt_text=prompt_text,
    )
    return _to_template_response(row)


@router.get("/prompt-templates/{template_id}")
async def prompts_test_get_prompt_template(
    template_id: str,
    auth: AuthContext = Depends(get_prompts_test_auth),
):
    safe_id = _validate_template_id(template_id)
    try:
        row = prompt_template_store.get_template(auth.user_id, safe_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Prompt template not found") from exc
    return _to_template_response(row)


@router.put("/prompt-templates/{template_id}")
async def prompts_test_update_prompt_template(
    template_id: str,
    payload: PromptTemplateUpdateRequest,
    auth: AuthContext = Depends(get_prompts_test_auth),
):
    safe_id = _validate_template_id(template_id)
    if payload.name is None and payload.prompt_text is None:
        raise HTTPException(status_code=400, detail="Provide name and/or prompt_text")

    name = _sanitize_template_text(payload.name, "name") if payload.name is not None else None
    prompt_text = (
        _sanitize_template_text(payload.prompt_text, "prompt_text") if payload.prompt_text is not None else None
    )

    try:
        row = prompt_template_store.update_template(
            user_id=auth.user_id,
            template_id=safe_id,
            name=name,
            prompt_text=prompt_text,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Prompt template not found") from exc
    return _to_template_response(row)


@router.delete("/prompt-templates/{template_id}")
async def prompts_test_delete_prompt_template(
    template_id: str,
    auth: AuthContext = Depends(get_prompts_test_auth),
):
    safe_id = _validate_template_id(template_id)
    try:
        prompt_template_store.delete_template(auth.user_id, safe_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Prompt template not found") from exc
    return {"status": "deleted", "id": safe_id}


# ============================================================================
# PIPELINE BUILDER & EXECUTION ENDPOINTS
# ============================================================================

import yaml

PIPELINES_DIR = BACKEND_ROOT.parent / "common_resources" / "templates"

class PipelineRunRequest(BaseModel):
    pipeline_yaml: str
    inputs: dict = Field(default_factory=dict)
    run_stages: list[str] | None = None
    mock_outputs: dict = Field(default_factory=dict)


@router.get("/pipelines")
async def list_pipelines(_auth: AuthContext = Depends(get_prompts_test_auth)):
    PIPELINES_DIR.mkdir(parents=True, exist_ok=True)
    pipelines = []
    for template_dir in PIPELINES_DIR.iterdir():
        if template_dir.is_dir():
            path = template_dir / "pipeline.yaml"
            if path.exists() and path.is_file():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = yaml.safe_load(f) or {}
                    pipelines.append({
                        "id": template_dir.name,
                        "name": content.get("name", template_dir.name),
                        "description": content.get("description", ""),
                        "version": content.get("version", 1)
                    })
                except Exception:
                    pipelines.append({
                        "id": template_dir.name,
                        "name": template_dir.name,
                        "description": "Failed to parse YAML metadata",
                        "version": 1
                    })
    return {"pipelines": pipelines}


def _new_run_dir(runs_root: Path, pipeline_id: str) -> Path:
    runs_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp}_{pipeline_id}"
    run_dir = runs_root / base_name
    counter = 1
    while run_dir.exists():
        run_dir = runs_root / f"{base_name}_{counter}"
        counter += 1
    run_dir.mkdir(parents=True)
    return run_dir


@router.post("/pipelines/run")
async def run_pipeline(
    payload: PipelineRunRequest,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    try:
        pipeline_data = yaml.safe_load(payload.pipeline_yaml)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid pipeline YAML: {exc}")

    from engine.validate_pipeline import validate_pipeline_data
    try:
        validate_pipeline_data(pipeline_data, BACKEND_ROOT)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Pipeline validation failed: {exc}")

    from engine.executor import PipelineRunFailure
    from engine.executor import run_pipeline as execute_pipeline
    from engine.inputs import InputResolutionError, resolve_inputs

    try:
        resolved_inputs = resolve_inputs(pipeline_data.get("inputs") or {}, payload.inputs)
    except InputResolutionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    stages = pipeline_data.get("stages", [])
    stage_ids = {s["id"] for s in stages if s.get("id")}
    run_stages = set(payload.run_stages) if payload.run_stages is not None else stage_ids

    run_dir = _new_run_dir(_default_runs_root(), pipeline_data.get("id", "pipeline"))
    started_iso = datetime.now(timezone.utc).isoformat()

    try:
        result = execute_pipeline(
            pipeline_data,
            resolved_inputs,
            root=BACKEND_ROOT,
            run_dir=run_dir,
            user_id=_auth.user_id,
            run_stages=run_stages,
            mock_outputs=payload.mock_outputs,
        )
        overall_status = "completed"
        failure_reason = None
    except PipelineRunFailure as exc:
        result = {"outputs": exc.outputs, "stage_results": exc.stage_results}
        overall_status = "failed"
        failure_reason = str(exc)
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    manifest = {
        "run_id": run_dir.name,
        "pipeline_id": pipeline_data.get("id"),
        "started_at_utc": started_iso,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "inputs": resolved_inputs,
        "run_stages": sorted(run_stages),
        "stage_results": result["stage_results"],
        "overall_status": overall_status,
        "failure_reason": failure_reason,
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "pipeline.yaml").write_text(payload.pipeline_yaml, encoding="utf-8")

    if overall_status == "failed":
        raise HTTPException(status_code=500, detail=failure_reason)

    return {
        "status": "completed",
        "run_id": run_dir.name,
        "outputs": result["outputs"],
        "manifest": manifest,
    }


@router.get("/pipelines/{pipeline_id}")
async def get_pipeline(pipeline_id: str, _auth: AuthContext = Depends(get_prompts_test_auth)):
    if "/" in pipeline_id or "\\" in pipeline_id or pipeline_id.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid pipeline ID")
    path = PIPELINES_DIR / pipeline_id / "pipeline.yaml"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Pipeline not found")
    return Response(content=path.read_text(encoding="utf-8"), media_type="text/yaml")


@router.post("/pipelines/{pipeline_id}")
async def save_pipeline(
    pipeline_id: str,
    body: str = Body(..., description="Raw YAML content"),
    _auth: AuthContext = Depends(get_prompts_test_auth)
):
    if "/" in pipeline_id or "\\" in pipeline_id or pipeline_id.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid pipeline ID")
    try:
        yaml.safe_load(body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML content: {exc}")
        
    template_dir = PIPELINES_DIR / pipeline_id
    template_dir.mkdir(parents=True, exist_ok=True)
    path = template_dir / "pipeline.yaml"
    path.write_text(body, encoding="utf-8")
    return {"status": "saved", "id": pipeline_id}


@router.delete("/pipelines/{pipeline_id}")
async def delete_pipeline(pipeline_id: str, _auth: AuthContext = Depends(get_prompts_test_auth)):
    if "/" in pipeline_id or "\\" in pipeline_id or pipeline_id.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid pipeline ID")
    template_dir = PIPELINES_DIR / pipeline_id
    if not template_dir.exists() or not template_dir.is_dir():
        raise HTTPException(status_code=404, detail="Pipeline not found")
    import shutil
    try:
        shutil.rmtree(template_dir)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete directory: {exc}")
    return {"status": "deleted", "id": pipeline_id}


@router.get("/pipeline-templates")
async def list_pipeline_templates(_auth: AuthContext = Depends(get_prompts_test_auth)):
    templates = []
    for template_name in ["duo_long", "solo_short"]:
        path = PIPELINES_DIR / template_name / "pipeline.yaml"
        if path.exists():
            try:
                yaml_content = path.read_text(encoding="utf-8")
                content = yaml.safe_load(yaml_content) or {}
                templates.append({
                    "id": template_name,
                    "name": content.get("name", template_name),
                    "description": content.get("description", ""),
                    "yaml": yaml_content
                })
            except Exception:
                pass
    return {"templates": templates}

