"""Routes: isolated prompts_test API for UI-driven prompt lab workflows."""

from __future__ import annotations

from dataclasses import dataclass
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any, Literal, Mapping

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from podcast_maker.core.hosts_config import AVAILABLE_HOSTS
from podcast_maker.core.paths import BACKEND_ROOT
from podcast_maker.core.prompt_manager import PodcastConfig
from podcast_maker.services import prompt_template_store
from prompts_test.prompt_resolver import InstrumentedOverridePromptManager
from prompts_test.compare import compare_files, list_run_directories, resolve_run_dir
from prompts_test.io_contracts import ContractError, STAGE_ORDER
from prompts_test.stage_runner import PromptTestRunner, RunnerInputs

router = APIRouter(prefix="/prompts-test-api", tags=["prompts-test-api"])

TASKS: dict[str, dict] = {}
LOCAL_USER_ID = "lab-local-user"
ALLOWED_FILES = {
    "run_manifest.json",
    "blueprint.json",
    "blueprint.snapshot.json",
    "research.md",
    "research.snapshot.md",
    "outline.json",
    "outline.snapshot.json",
    "script.txt",
    "script.snapshot.txt",
    "prompt_architect.txt",
    "prompt_researcher.txt",
    "prompt_outliner.txt",
    "prompt_scriptwriter.txt",
    "pipeline.yaml",
}


class InjectedInputPayload(BaseModel):
    blueprint_path: str | None = None
    blueprint_json: dict | None = None
    research_path: str | None = None
    research_text: str | None = None
    outline_path: str | None = None
    outline_json: dict | None = None


class PromptOverridePayload(BaseModel):
    path: str | None = None
    text: str | None = None


class PromptOverridesPayload(BaseModel):
    architect: PromptOverridePayload | None = None
    researcher: PromptOverridePayload | None = None
    outliner: PromptOverridePayload | None = None
    scriptwriter: PromptOverridePayload | None = None


class PromptsTestRunRequest(BaseModel):
    topic: str = Field(min_length=1)
    stages: list[Literal["architect", "researcher", "outliner", "scriptwriter"]] = Field(
        default_factory=lambda: ["architect", "researcher", "outliner", "scriptwriter"]
    )
    format: Literal["dialogue", "solo"] | None = None
    host_ids: list[str] | None = None
    run_name: str | None = None
    runs_root: str | None = None
    injected: InjectedInputPayload = Field(default_factory=InjectedInputPayload)
    prompt_overrides: PromptOverridesPayload = Field(default_factory=PromptOverridesPayload)
    async_mode: bool = True


class CompareRequest(BaseModel):
    run_a: str
    run_b: str
    file_name: str = "research.md"
    max_lines: int = 200
    runs_root: str | None = None


class DefaultsRequest(BaseModel):
    topic: str
    format: Literal["dialogue", "solo"] | None = None
    host_ids: list[str] | None = None
    injected: InjectedInputPayload = Field(default_factory=InjectedInputPayload)


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


def _sanitize_topic_text(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="topic is required")
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


def _write_temp_json(directory: Path, file_name: str, payload: dict) -> Path:
    target = directory / file_name
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _write_temp_text(directory: Path, file_name: str, payload: str) -> Path:
    target = directory / file_name
    target.write_text(payload, encoding="utf-8")
    return target


def _resolve_injected_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value)


def _resolve_override_path(value: PromptOverridePayload | None, temp_dir: Path, stage: str) -> Path | None:
    if value is None:
        return None

    if value.path and value.text:
        raise ContractError(f"Provide either path or text for {stage} override, not both.")

    if value.path:
        return Path(value.path)

    if value.text is not None:
        return _write_temp_text(temp_dir, f"override_{stage}.md", value.text)

    return None


def _build_runner_inputs(request: PromptsTestRunRequest, temp_dir: Path) -> RunnerInputs:
    injected = request.injected

    if injected.blueprint_path and injected.blueprint_json is not None:
        raise ContractError("Provide blueprint_path or blueprint_json, not both.")
    if injected.research_path and injected.research_text is not None:
        raise ContractError("Provide research_path or research_text, not both.")
    if injected.outline_path and injected.outline_json is not None:
        raise ContractError("Provide outline_path or outline_json, not both.")

    blueprint_file = _resolve_injected_path(injected.blueprint_path)
    if injected.blueprint_json is not None:
        blueprint_file = _write_temp_json(temp_dir, "injected_blueprint.json", injected.blueprint_json)

    research_file = _resolve_injected_path(injected.research_path)
    if injected.research_text is not None:
        research_file = _write_temp_text(temp_dir, "injected_research.md", injected.research_text)

    outline_file = _resolve_injected_path(injected.outline_path)
    if injected.outline_json is not None:
        outline_file = _write_temp_json(temp_dir, "injected_outline.json", injected.outline_json)

    overrides = request.prompt_overrides
    override_architect = _resolve_override_path(overrides.architect, temp_dir, "architect")
    override_researcher = _resolve_override_path(overrides.researcher, temp_dir, "researcher")
    override_outliner = _resolve_override_path(overrides.outliner, temp_dir, "outliner")
    override_scriptwriter = _resolve_override_path(overrides.scriptwriter, temp_dir, "scriptwriter")

    stages_arg = ",".join(request.stages)
    runs_root = _resolve_runs_root(request.runs_root)

    return RunnerInputs(
        topic=request.topic,
        stages_arg=stages_arg,
        host_ids=request.host_ids,
        podcast_format=request.format,
        blueprint_file=blueprint_file,
        research_file=research_file,
        outline_file=outline_file,
        runs_root=runs_root,
        run_name=request.run_name,
        prompt_override_architect=override_architect,
        prompt_override_researcher=override_researcher,
        prompt_override_outliner=override_outliner,
        prompt_override_scriptwriter=override_scriptwriter,
    )


def _read_manifest(run_dir: Path) -> dict | None:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _get_stage_response_file(pipeline_data: dict, stage_id: str, template_dir: Path) -> Path | None:
    for stage in pipeline_data.get("stages", []):
        if stage.get("id") == stage_id:
            response_spec = stage.get("response", {})
            file_path_str = response_spec.get("file") or response_spec.get("aggregate_file")
            if file_path_str:
                return template_dir / file_path_str
    return None


def _resolve_default_inputs_dynamic(payload: DefaultsRequest, template_dir: Path, pipeline_data: dict) -> tuple[dict, str, dict]:
    injected = payload.injected

    if injected.blueprint_json is not None:
        blueprint = injected.blueprint_json
    elif injected.blueprint_path:
        blueprint = json.loads(Path(injected.blueprint_path).read_text(encoding="utf-8"))
    else:
        blueprint_file = _get_stage_response_file(pipeline_data, "architect", template_dir)
        if blueprint_file and blueprint_file.is_file():
            blueprint = json.loads(blueprint_file.read_text(encoding="utf-8"))
        else:
            blueprint = {}

    if injected.research_text is not None:
        research = injected.research_text
    elif injected.research_path:
        research = Path(injected.research_path).read_text(encoding="utf-8")
    else:
        research_file = _get_stage_response_file(pipeline_data, "researcher", template_dir)
        if research_file and research_file.is_file():
            research = research_file.read_text(encoding="utf-8")
        else:
            research = ""

    if injected.outline_json is not None:
        outline = injected.outline_json
    elif injected.outline_path:
        outline = json.loads(Path(injected.outline_path).read_text(encoding="utf-8"))
    else:
        outline_file = _get_stage_response_file(pipeline_data, "outliner", template_dir)
        if outline_file and outline_file.is_file():
            outline = json.loads(outline_file.read_text(encoding="utf-8"))
        else:
            outline = {}

    return blueprint, research, outline


def _run_and_collect(request: PromptsTestRunRequest) -> dict:
    with tempfile.TemporaryDirectory(prefix="prompts_test_api_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        runner_inputs = _build_runner_inputs(request, temp_dir)
        runner = PromptTestRunner(runner_inputs)
        run_dir = runner.run()
        manifest = _read_manifest(run_dir)

    return {
        "run_id": run_dir.name,
        "run_directory": str(run_dir),
        "manifest": manifest,
    }


def _run_task(task_id: str, request: PromptsTestRunRequest) -> None:
    try:
        result = _run_and_collect(request)
        TASKS[task_id] = {"status": "completed", "result": result}
    except Exception as exc:
        TASKS[task_id] = {"status": "failed", "error": str(exc)}


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
        "stages": STAGE_ORDER,
        "default_host_ids": ["sarah_curious", "mike_expert"],
        "hosts": hosts,
        "default_runs_root": str(_default_runs_root()),
    }


@router.post("/defaults")
async def prompts_test_defaults(
    payload: DefaultsRequest,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    try:
        host_ids = payload.host_ids or ["sarah_curious", "mike_expert"]
        config = PodcastConfig(topic=payload.topic, host_ids=host_ids, format=payload.format)

        template_name = "solo_short" if config.effective_format == "solo" else "duo_long"
        template_dir = PIPELINES_DIR / template_name
        pipeline_yaml_path = template_dir / "pipeline.yaml"
        if not pipeline_yaml_path.exists():
            raise FileNotFoundError(f"Default pipeline template not found at {pipeline_yaml_path}")

        pipeline_data = yaml.safe_load(pipeline_yaml_path.read_text(encoding="utf-8")) or {}
        blueprint, research, outline = _resolve_default_inputs_dynamic(payload, template_dir, pipeline_data)

        with tempfile.TemporaryDirectory(prefix="defaults_overrides_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            overrides = {}
            for stage_data in pipeline_data.get("stages", []):
                stage_id = stage_data.get("id")
                if stage_id:
                    prompt_text = _resolve_yaml_stage_prompt(stage_data, BACKEND_ROOT, LOCAL_USER_ID)
                    if prompt_text is not None:
                        overrides[stage_id] = _write_temp_text(temp_dir, f"default_override_{stage_id}.md", prompt_text)

            prompt_manager = InstrumentedOverridePromptManager(config, overrides=overrides)

            architect_prompt = prompt_manager.get_architect_prompt()
            # Use first segment to build a representative researcher prompt preview.
            representative_segment = blueprint.get("segments", [{}])[0] if isinstance(blueprint, dict) else {}
            researcher_prompt = prompt_manager.get_researcher_prompt(representative_segment)
            outliner_prompt = prompt_manager.get_outliner_prompt(blueprint, research, payload.topic)
            scriptwriter_prompt = prompt_manager.get_scriptwriter_prompt(
                outline, research, "--- This is Scene 1 - start with the opening ---\n\n"
            )

        return {
            "topic": payload.topic,
            "format": config.effective_format,
            "host_ids": host_ids,
            "prompts": {
                "architect": architect_prompt,
                "researcher": researcher_prompt,
                "outliner": outliner_prompt,
                "scriptwriter": scriptwriter_prompt,
            },
            "outputs": {
                "architect": json.dumps(blueprint, ensure_ascii=False, indent=2),
                "researcher": research,
                "outliner": json.dumps(outline, ensure_ascii=False, indent=2),
                "scriptwriter": "",
            },
        }
    except (ContractError, FileNotFoundError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
                "topic": (manifest or {}).get("topic"),
                "stages": (manifest or {}).get("stages", []),
                "created_at_utc": (manifest or {}).get("created_at_utc"),
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


@router.get("/runs/{run_id}/files/{file_name}")
async def prompts_test_run_file(
    run_id: str,
    file_name: str,
    runs_root: str | None = None,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    if "/" in file_name or "\\" in file_name or file_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid file name")

    root = _resolve_runs_root(runs_root)
    run_dir = resolve_run_dir(root, run_id)
    target = run_dir / file_name

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if file_name not in ALLOWED_FILES and not file_name.startswith("prompt_"):
        raise HTTPException(status_code=403, detail="File is not exposed by this API")

    return {
        "run_id": run_dir.name,
        "file_name": file_name,
        "content": target.read_text(encoding="utf-8", errors="replace"),
    }


@router.post("/runs")
async def prompts_test_create_run(
    payload: PromptsTestRunRequest,
    background_tasks: BackgroundTasks,
    _auth: AuthContext = Depends(get_prompts_test_auth),
):
    try:
        payload.topic = _sanitize_topic_text(payload.topic)

        if payload.async_mode:
            task_id = str(uuid.uuid4())
            TASKS[task_id] = {"status": "running"}
            background_tasks.add_task(_run_task, task_id, payload)
            return {"task_id": task_id, "status": "running"}

        result = _run_and_collect(payload)
        return {"status": "completed", "result": result}
    except (ContractError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/tasks/{task_id}")
async def prompts_test_task_status(task_id: str, _auth: AuthContext = Depends(get_prompts_test_auth)):
    task = TASKS.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


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
    except (ContractError, FileNotFoundError) as exc:
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


def _resolve_yaml_stage_prompt(stage_data: dict, root_path: Path, user_id: str) -> str | None:
    prompt_spec = stage_data.get("prompt")
    if not prompt_spec or not isinstance(prompt_spec, dict):
        return None
    source = prompt_spec.get("source")
    if source == "inline":
        return prompt_spec.get("text")
    elif source == "file":
        prompt_path = prompt_spec.get("path")
        if prompt_path:
            full_path = root_path / prompt_path
            if full_path.is_file():
                return full_path.read_text(encoding="utf-8")
    elif source == "template":
        template_id = prompt_spec.get("template_id")
        if template_id:
            try:
                row = prompt_template_store.get_template(user_id, template_id)
                return row.get("prompt_text")
            except Exception:
                pass
    return None


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
    body: str = Field(..., description="Raw YAML content"),
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

    stages = pipeline_data.get("stages", [])
    stage_ids = [s.get("id") for s in stages if s.get("id")]
    run_stages = payload.run_stages if payload.run_stages is not None else stage_ids
    
    with tempfile.TemporaryDirectory(prefix="pipeline_run_") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        
        override_paths = {}
        for stage_data in stages:
            stage_id = stage_data.get("id")
            if not stage_id:
                continue
            prompt_text = _resolve_yaml_stage_prompt(stage_data, BACKEND_ROOT, _auth.user_id)
            if prompt_text is not None:
                override_paths[stage_id] = _write_temp_text(temp_dir, f"override_{stage_id}.md", prompt_text)
                
        blueprint_file = None
        research_file = None
        outline_file = None
        
        if "architect" not in run_stages and ("researcher" in run_stages or "outliner" in run_stages):
            mock_bp = payload.mock_outputs.get("architect", {}).get("blueprint") or payload.mock_outputs.get("architect", {})
            if mock_bp:
                blueprint_file = _write_temp_json(temp_dir, "mock_blueprint.json", mock_bp)
                
        if "researcher" not in run_stages and ("outliner" in run_stages or "scriptwriter" in run_stages):
            mock_res = payload.mock_outputs.get("researcher", {}).get("research") or payload.mock_outputs.get("researcher", "")
            if isinstance(mock_res, dict):
                mock_res = mock_res.get("research", "")
            if mock_res:
                research_file = _write_temp_text(temp_dir, "mock_research.md", mock_res)
                
        if "outliner" not in run_stages and "scriptwriter" in run_stages:
            mock_ol = payload.mock_outputs.get("outliner", {}).get("outline") or payload.mock_outputs.get("outliner", {})
            if mock_ol:
                outline_file = _write_temp_json(temp_dir, "mock_outline.json", mock_ol)

        topic = payload.inputs.get("topic", "").strip()
        if not topic:
            topic = "Default Topic"
            
        host_ids = payload.inputs.get("host_ids")
        podcast_format = payload.inputs.get("format")
        
        try:
            runner_inputs = RunnerInputs(
                topic=topic,
                stages_arg=",".join(run_stages),
                host_ids=host_ids,
                podcast_format=podcast_format,
                blueprint_file=blueprint_file,
                research_file=research_file,
                outline_file=outline_file,
                runs_root=_default_runs_root(),
                prompt_override_architect=override_paths.get("architect"),
                prompt_override_researcher=override_paths.get("researcher"),
                prompt_override_outliner=override_paths.get("outliner"),
                prompt_override_scriptwriter=override_paths.get("scriptwriter"),
            )
            
            runner = PromptTestRunner(runner_inputs)
            run_dir = runner.run()
            manifest = _read_manifest(run_dir)
            
            # Save the pipeline configuration YAML
            (run_dir / "pipeline.yaml").write_text(payload.pipeline_yaml, encoding="utf-8")
            
            outputs = {}
            for stage in run_stages:
                if stage == "architect" and (run_dir / "blueprint.json").exists():
                    outputs["architect"] = {"blueprint": json.loads((run_dir / "blueprint.json").read_text(encoding="utf-8"))}
                elif stage == "researcher" and (run_dir / "research.md").exists():
                    outputs["researcher"] = {"research": (run_dir / "research.md").read_text(encoding="utf-8")}
                elif stage == "outliner" and (run_dir / "outline.json").exists():
                    outputs["outliner"] = {"outline": json.loads((run_dir / "outline.json").read_text(encoding="utf-8"))}
                elif stage == "scriptwriter" and (run_dir / "script.txt").exists():
                    outputs["scriptwriter"] = {"script": (run_dir / "script.txt").read_text(encoding="utf-8")}

            return {
                "status": "completed",
                "run_id": run_dir.name,
                "outputs": outputs,
                "manifest": manifest
            }
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

