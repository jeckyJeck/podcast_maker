"""Sandboxed per-run workspace for the optimization agent.

The agent must never edit `common_resources/templates/*/pipeline.yaml` directly.
Instead, `start_workspace()` extracts each stage's inline prompt text into its own
`.md` file inside a throwaway workspace directory. The agent's `read_file` /
`write_file` / `edit_file` tools are confined to that directory (see `tools.py`'s
`CONTENT_ROOT`). The only way a workspace edit reaches the real pipeline file is the
explicit `promote_prompt()` call below.
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

ROOT = Path(__file__).resolve().parent
WORKSPACE_DIR = ROOT / "workspace"
COMMON_RESOURCES = ROOT.parent / "common_resources"


@dataclass
class WorkspaceInfo:
    workspace_id: str
    root: Path
    format: str
    pipeline_source: Path
    stage_ids: list[str]


def _pipeline_path(format: str) -> Path:
    path = COMMON_RESOURCES / "templates" / format / "pipeline.yaml"
    if not path.exists():
        raise ValueError(f"No pipeline template found for format {format!r} at {path}")
    return path


def _manifest_path(workspace_root: Path) -> Path:
    return workspace_root / "manifest.json"


def start_workspace(format: str) -> WorkspaceInfo:
    """Extract the real pipeline's inline prompts into a fresh sandboxed workspace."""
    pipeline_path = _pipeline_path(format)
    pipeline_data = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}

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
        stage_file = prompts_dir / f"{stage_id}.md"
        stage_file.write_text(prompt_spec.get("text", ""), encoding="utf-8")
        stage_ids.append(stage_id)
        manifest_stages[stage_id] = {
            "workspace_file": f"prompts/{stage_id}.md",
            "execution": stage.get("execution"),
        }

    (workspace_root / "pipeline.yaml").write_text(
        pipeline_path.read_text(encoding="utf-8"), encoding="utf-8"
    )

    manifest = {
        "workspace_id": workspace_id,
        "format": format,
        "pipeline_source": str(pipeline_path.relative_to(ROOT.parent)).replace("\\", "/"),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stages": manifest_stages,
    }
    _manifest_path(workspace_root).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return WorkspaceInfo(
        workspace_id=workspace_id,
        root=workspace_root,
        format=format,
        pipeline_source=pipeline_path,
        stage_ids=stage_ids,
    )


def _load_manifest(workspace_root: Path) -> dict[str, Any]:
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


def read_source_prompt_text(workspace_root: Path, stage_id: str) -> str:
    """Re-read the *current* real prompt text for a stage, live from common_resources."""
    manifest = _load_manifest(workspace_root)
    _stage_entry(manifest, stage_id)
    pipeline_path = ROOT.parent / manifest["pipeline_source"]
    pipeline_data = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
    for stage in pipeline_data.get("stages", []):
        if stage.get("id") == stage_id:
            return (stage.get("prompt") or {}).get("text", "")
    raise ValueError(f"Stage {stage_id!r} no longer exists in {pipeline_path}")


def diff_against_source(workspace_root: Path, stage_id: str) -> str:
    manifest = _load_manifest(workspace_root)
    entry = _stage_entry(manifest, stage_id)
    workspace_text = (workspace_root / entry["workspace_file"]).read_text(encoding="utf-8")
    source_text = read_source_prompt_text(workspace_root, stage_id)
    diff = difflib.unified_diff(
        source_text.splitlines(keepends=True),
        workspace_text.splitlines(keepends=True),
        fromfile=f"common_resources (current) :: {stage_id}",
        tofile=f"workspace (your edit) :: {stage_id}",
    )
    return "".join(diff) or "(no differences)"


def promote_prompt(workspace_root: Path, stage_id: str) -> str:
    """Write the workspace's edited prompt text back into the real pipeline.yaml."""
    manifest = _load_manifest(workspace_root)
    entry = _stage_entry(manifest, stage_id)
    workspace_file = workspace_root / entry["workspace_file"]
    if not workspace_file.exists():
        raise ValueError(f"Workspace file missing: {workspace_file}")
    new_text = workspace_file.read_text(encoding="utf-8")

    pipeline_path = ROOT.parent / manifest["pipeline_source"]
    pipeline_data = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
    for stage in pipeline_data.get("stages", []):
        if stage.get("id") == stage_id:
            old_text = (stage.get("prompt") or {}).get("text", "")
            stage.setdefault("prompt", {})["text"] = new_text
            break
    else:
        raise ValueError(f"Stage {stage_id!r} no longer exists in {pipeline_path}")

    pipeline_path.write_text(
        yaml.safe_dump(pipeline_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    diff = difflib.unified_diff(
        old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"before :: {stage_id}",
        tofile=f"after :: {stage_id}",
    )
    diff_text = "".join(diff) or "(no differences)"
    return f"Promoted {stage_id} to {pipeline_path.relative_to(ROOT.parent)}\n{diff_text}"
