"""Routes: isolated prompts_test API for UI-driven prompt lab workflows."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import AuthContext, get_current_user
from podcast_maker.core.hosts_config import AVAILABLE_HOSTS
from podcast_maker.core.prompt_manager import PodcastConfig
from podcast_maker.services import prompt_template_store
from prompts_test.prompt_resolver import InstrumentedOverridePromptManager
from prompts_test.compare import compare_files, list_run_directories, resolve_run_dir
from prompts_test.io_contracts import ContractError, STAGE_ORDER
from prompts_test.stage_runner import PromptTestRunner, RunnerInputs

router = APIRouter(prefix="/prompts-test-api", tags=["prompts-test-api"])

TASKS: dict[str, dict] = {}
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
    topic: str = "ford fulkerson"
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


def _sanitize_template_text(value: str, field_name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail=f"{field_name} cannot be empty")
    return cleaned


def _validate_template_id(template_id: str) -> str:
    if not prompt_template_store.is_valid_template_id(template_id):
        raise HTTPException(status_code=400, detail="Invalid template id")
    return template_id


def _to_template_response(row: dict) -> PromptTemplateResponse:
    return PromptTemplateResponse(
        id=str(row.get("id", "")),
        user_id=str(row.get("user_id", "")),
        stage=row.get("stage", "architect"),
        name=str(row.get("name", "")),
        prompt_text=str(row.get("prompt_text", "")),
        created_at_utc=str(row.get("created_at_utc", "")),
        updated_at_utc=str(row.get("updated_at_utc", "")),
    )


def _is_local_auth_bypass_enabled() -> bool:
    return os.getenv("PROMPTS_TEST_API_BYPASS_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}


async def get_prompts_test_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    """Auth dependency scoped to prompts_test API only.

    - Default behavior: enforce regular Supabase JWT auth via get_current_user.
    - Local-dev behavior: when PROMPTS_TEST_API_BYPASS_AUTH is truthy, bypass auth.
    """
    if _is_local_auth_bypass_enabled():
        return AuthContext(user_id="local-dev", method="bypass")
    return await get_current_user(authorization)


def _default_runs_root() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts_test" / "runs"


def _default_fixtures_root() -> Path:
    return Path(__file__).resolve().parents[2] / "prompts_test" / "fixtures"


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


def _load_default_fixture_json(name: str) -> dict:
    path = _default_fixtures_root() / name
    return json.loads(path.read_text(encoding="utf-8"))


def _load_default_fixture_text(name: str) -> str:
    path = _default_fixtures_root() / name
    return path.read_text(encoding="utf-8")


def _resolve_default_inputs(payload: DefaultsRequest) -> tuple[dict, str, dict]:
    injected = payload.injected

    if injected.blueprint_json is not None:
        blueprint = injected.blueprint_json
    elif injected.blueprint_path:
        blueprint = json.loads(Path(injected.blueprint_path).read_text(encoding="utf-8"))
    else:
        blueprint = _load_default_fixture_json("blueprint.sample.json")

    if injected.research_text is not None:
        research = injected.research_text
    elif injected.research_path:
        research = Path(injected.research_path).read_text(encoding="utf-8")
    else:
        research = _load_default_fixture_text("research.sample.md")

    if injected.outline_json is not None:
        outline = injected.outline_json
    elif injected.outline_path:
        outline = json.loads(Path(injected.outline_path).read_text(encoding="utf-8"))
    else:
        outline = _load_default_fixture_json("outline.sample.json")

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
        "default_topic": "ford fulkerson",
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
        prompt_manager = InstrumentedOverridePromptManager(config)

        blueprint, research, outline = _resolve_default_inputs(payload)

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
