"""Sandboxed per-run workspace for the optimization agent.

The agent never edits the backend's pipeline directly. `start_workspace()` fetches a
pipeline from the backend (GET /prompts-test-api/pipelines/{id}) and extracts each
stage's inline prompt text into its own `.md` file inside a throwaway workspace
directory. The agent's `read_file` / `write_file` / `edit_file` tools are confined to
that directory (see `tools.py`'s `CONTENT_ROOT`).

Workspace edits reach the backend in two ways only:
  * `build_pipeline_yaml()` - the edited pipeline is sent inline with each run request,
    so experiments never touch the backend's stored pipeline;
  * `promote_prompt()` - the explicit, opt-in save of an edited prompt back to the
    backend (POST /prompts-test-api/pipelines/{id}).
"""

from __future__ import annotations

import difflib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

try:
    from . import backend_client
except ImportError:  # pragma: no cover - supports direct script execution
    import backend_client

ROOT = Path(__file__).resolve().parent
WORKSPACE_DIR = ROOT / "workspace"


@dataclass
class WorkspaceInfo:
    workspace_id: str
    root: Path
    format: str  # backend pipeline id
    stage_ids: list[str]


def _manifest_path(workspace_root: Path) -> Path:
    return workspace_root / "manifest.json"


def _dump_yaml(pipeline_data: dict[str, Any]) -> str:
    return yaml.safe_dump(pipeline_data, allow_unicode=True, sort_keys=False)


def start_workspace(format: str) -> WorkspaceInfo:
    """Fetch the backend pipeline and extract its inline prompts into a fresh workspace."""
    pipeline_text = backend_client.get_pipeline_yaml(format)
    pipeline_data = yaml.safe_load(pipeline_text) or {}

    workspace_id = f"ws_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid.uuid4().hex[:6]}"
    workspace_root = WORKSPACE_DIR / workspace_id
    prompts_dir = workspace_root / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    stage_ids: list[str] = []
    manifest_stages: dict[str, Any] = {}
    for stage in pipeline_data.get("stages", []):
        stage_id = stage.get("id")
        prompt_spec = stage.get("prompt") or {}
        if not stage_id or prompt_spec.get("source") != "inline":
            continue
        (prompts_dir / f"{stage_id}.md").write_text(prompt_spec.get("text", ""), encoding="utf-8")
        stage_ids.append(stage_id)
        manifest_stages[stage_id] = {
            "workspace_file": f"prompts/{stage_id}.md",
            "execution": stage.get("execution"),
        }

    (workspace_root / "pipeline.yaml").write_text(pipeline_text, encoding="utf-8")
    manifest = {
        "workspace_id": workspace_id,
        "format": format,
        "pipeline_id": pipeline_data.get("id", format),
        "backend_url": backend_client.BACKEND_URL,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stages": manifest_stages,
    }
    _manifest_path(workspace_root).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return WorkspaceInfo(workspace_id=workspace_id, root=workspace_root, format=format, stage_ids=stage_ids)


def load_manifest(workspace_root: Path) -> dict[str, Any]:
    manifest_path = _manifest_path(workspace_root)
    if not manifest_path.exists():
        raise ValueError(f"No workspace manifest at {manifest_path}; call start_workspace first")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _stage_entry(manifest: dict[str, Any], stage_id: str) -> dict[str, Any]:
    stages = manifest.get("stages", {})
    if stage_id not in stages:
        known = ", ".join(sorted(stages)) or "(none)"
        raise ValueError(f"Unknown stage_id {stage_id!r} for this workspace. Known stages: {known}")
    return stages[stage_id]


def _prompt_text_from_yaml(pipeline_yaml: str, stage_id: str) -> str:
    for stage in (yaml.safe_load(pipeline_yaml) or {}).get("stages", []):
        if stage.get("id") == stage_id:
            return (stage.get("prompt") or {}).get("text", "")
    raise ValueError(f"Stage {stage_id!r} does not exist in that pipeline")


def read_source_prompt_text(workspace_root: Path, stage_id: str) -> str:
    """Re-read the *current* prompt text for a stage, live from the backend."""
    manifest = load_manifest(workspace_root)
    _stage_entry(manifest, stage_id)
    return _prompt_text_from_yaml(backend_client.get_pipeline_yaml(manifest["pipeline_id"]), stage_id)


def build_pipeline_yaml(workspace_root: Path) -> str:
    """The workspace pipeline with every stage's edited prompt text applied (in-memory sandbox copy)."""
    manifest = load_manifest(workspace_root)
    pipeline_data = yaml.safe_load((workspace_root / "pipeline.yaml").read_text(encoding="utf-8")) or {}
    for stage in pipeline_data.get("stages", []):
        entry = manifest["stages"].get(stage.get("id"))
        if entry:
            stage["prompt"]["text"] = (workspace_root / entry["workspace_file"]).read_text(encoding="utf-8")
    return _dump_yaml(pipeline_data)


def diff_against_source(workspace_root: Path, stage_id: str) -> str:
    manifest = load_manifest(workspace_root)
    entry = _stage_entry(manifest, stage_id)
    workspace_text = (workspace_root / entry["workspace_file"]).read_text(encoding="utf-8")
    source_text = read_source_prompt_text(workspace_root, stage_id)
    diff = difflib.unified_diff(
        source_text.splitlines(keepends=True),
        workspace_text.splitlines(keepends=True),
        fromfile=f"backend (current) :: {stage_id}",
        tofile=f"workspace (your edit) :: {stage_id}",
    )
    return "".join(diff) or "(no differences)"


def restore_prompt_from_run(workspace_root: Path, stage_id: str, run_id: str) -> str:
    """Overwrite a workspace prompt with the text the given backend run used."""
    manifest = load_manifest(workspace_root)
    entry = _stage_entry(manifest, stage_id)
    run_pipeline_yaml = backend_client.read_run_file(run_id, "pipeline.yaml")
    if run_pipeline_yaml is None:
        raise ValueError(f"Run {run_id} has no pipeline.yaml snapshot")
    (workspace_root / entry["workspace_file"]).write_text(
        _prompt_text_from_yaml(run_pipeline_yaml, stage_id), encoding="utf-8"
    )
    return "ok"


def promote_prompt(workspace_root: Path, stage_id: str) -> str:
    """Save the workspace's edited prompt for one stage back to the backend pipeline."""
    manifest = load_manifest(workspace_root)
    entry = _stage_entry(manifest, stage_id)
    new_text = (workspace_root / entry["workspace_file"]).read_text(encoding="utf-8")

    pipeline_id = manifest["pipeline_id"]
    pipeline_data = yaml.safe_load(backend_client.get_pipeline_yaml(pipeline_id)) or {}
    for stage in pipeline_data.get("stages", []):
        if stage.get("id") == stage_id:
            old_text = (stage.get("prompt") or {}).get("text", "")
            stage.setdefault("prompt", {})["text"] = new_text
            break
    else:
        raise ValueError(f"Stage {stage_id!r} no longer exists in backend pipeline {pipeline_id!r}")

    backend_client.save_pipeline_yaml(pipeline_id, _dump_yaml(pipeline_data))

    diff = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"before :: {stage_id}",
        tofile=f"after :: {stage_id}",
    )
    return f"Promoted {stage_id} to backend pipeline {pipeline_id}\n{''.join(diff) or '(no differences)'}"
