from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    from .agent_llm import ToolSpec
    from . import backend_client
    from . import workspace as workspace_module
except ImportError:  # pragma: no cover - supports direct script execution
    from agent_llm import ToolSpec
    import backend_client
    import workspace as workspace_module


ROOT = Path(__file__).resolve().parent
EXPERIMENTS_DIR = ROOT / "experiments"
TEST_TOPICS_PATH = ROOT / "test_topics.yaml"

# Files a pipeline run writes into its run directory on the backend.
STAGE_FILES = {
    "script": "outputs/script.txt",
    "outline": "outputs/outline.json",
    "blueprint": "outputs/blueprint.json",
    "research": "outputs/research.md",
}
MAX_LISTED_RUNS = 30

# Set by agent.py at startup once a workspace exists. read_file/write_file/edit_file
# resolve against this instead of ROOT so the agent can never touch files outside its
# sandboxed workspace copy. promote_prompt is the only path back to the backend's pipeline.
CONTENT_ROOT: Path | None = None
PROMOTE_ENABLED: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_content_path(path: str) -> Path:
    """Resolve a path for read_file/write_file/edit_file/diff_files against the active workspace.

    Confines content edits to CONTENT_ROOT (the sandboxed workspace) so the agent can
    never write anywhere outside its own copy.
    """
    base = (CONTENT_ROOT or ROOT).resolve()
    candidate = (base / path).resolve()
    if base not in candidate.parents and candidate != base:
        raise ValueError(f"Path escapes workspace root: {path}")
    return candidate


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _json_or_none(text: str | None) -> Any | None:
    return json.loads(text) if text else None


def read_file(path: str) -> str:
    """Read a file and return its contents as a string."""
    try:
        file_path = safe_content_path(path)
        if not file_path.exists():
            return f"error: file does not exist: {path}"
        return file_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it if it does not exist."""
    try:
        file_path = safe_content_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return "ok"
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def edit_file(path: str, old_text: str, new_text: str, replace_all: bool = False) -> str:
    """Replace an exact text segment within an existing file (paragraph-level edit, not a full rewrite)."""
    try:
        file_path = safe_content_path(path)
        if not file_path.exists():
            return f"error: file does not exist: {path}"
        content = file_path.read_text(encoding="utf-8")
        count = content.count(old_text)
        if count == 0:
            return "error: old_text not found in file"
        if count > 1 and not replace_all:
            return f"error: old_text is not unique ({count} occurrences); pass replace_all=true or include more context"
        updated = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
        file_path.write_text(updated, encoding="utf-8")
        return "ok"
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def run_summaries(limit: int = MAX_LISTED_RUNS) -> list[dict[str, Any]]:
    """Latest backend runs with their evaluation score (if evaluated)."""
    entries: list[dict[str, Any]] = []
    for run in sorted(backend_client.list_runs(), key=lambda r: r["run_id"])[-limit:]:
        evaluation = backend_client.get_evaluation(run["run_id"]) or {}
        entries.append(
            {
                "run_id": run["run_id"],
                "created_at": run.get("created_at_utc"),
                "topic": run.get("topic"),
                "overall_score": evaluation.get("overall_score"),
                "dimensions": evaluation.get("dimensions"),
            }
        )
    return entries


def list_runs() -> str:
    """Return a JSON list of the latest backend runs with their evaluation summaries."""
    try:
        return json.dumps(run_summaries(), ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def _read_run(run_id: str, stages: list[str]) -> str:
    try:
        data: dict[str, Any] = {
            "manifest": backend_client.get_run(run_id).get("manifest"),
            "evaluation": backend_client.get_evaluation(run_id),
        }
        for stage in stages:
            text = backend_client.read_run_file(run_id, STAGE_FILES[stage])
            data[stage] = _json_or_none(text) if STAGE_FILES[stage].endswith(".json") else text
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def read_run(run_id: str) -> str:
    """Return the manifest, evaluation and script of a run as a JSON object."""
    return _read_run(run_id, ["script"])


def read_run_full(run_id: str) -> str:
    """Return all major contents of a run as a JSON object."""
    return _read_run(run_id, ["blueprint", "research", "outline", "script"])


def diff_files(path_a: str, path_b: str) -> str:
    """Return a unified diff between two workspace files."""
    try:
        import difflib

        a = safe_content_path(path_a)
        b = safe_content_path(path_b)
        text_a = a.read_text(encoding="utf-8").splitlines(keepends=True)
        text_b = b.read_text(encoding="utf-8").splitlines(keepends=True)
        return "".join(difflib.unified_diff(text_a, text_b, fromfile=path_a, tofile=path_b))
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def diff_runs(run_id_a: str, run_id_b: str, stage: str = "script") -> str:
    """Return a diff of a specific output file between two runs."""
    if stage not in STAGE_FILES:
        return f"error: unknown stage: {stage}"
    try:
        return backend_client.compare_runs(run_id_a, run_id_b, STAGE_FILES[stage])
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def run_pipeline(topic: str, format: str, extra_inputs: dict | None = None) -> str:
    """Run the workspace's (edited) pipeline on the backend for a topic; returns the new run_id."""
    try:
        if CONTENT_ROOT is None:
            return "error: no workspace active"
        manifest = workspace_module.load_manifest(CONTENT_ROOT)
        if format != manifest["format"]:
            return f"error: this workspace edits pipeline {manifest['format']!r}; cannot run format {format!r}"
        pipeline_yaml = workspace_module.build_pipeline_yaml(CONTENT_ROOT)
        result = backend_client.run_pipeline(pipeline_yaml, {"topic": topic, **(extra_inputs or {})})
        return result["run_id"]
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: pipeline failed\n{exc}"


def run_evaluation(run_id: str) -> str:
    """Run the backend's LLM judge on a completed run (stored as the run's evaluation)."""
    try:
        context_files = {}
        if backend_client.read_run_file(run_id, STAGE_FILES["research"]) is not None:
            context_files["research"] = STAGE_FILES["research"]
        evaluation = backend_client.evaluate_run(
            run_id, content_files={"script": STAGE_FILES["script"]}, context_files=context_files or None
        )
        return json.dumps(
            {
                "run_id": run_id,
                "overall_score": evaluation.get("overall_score"),
                "dimension_scores": evaluation.get("dimensions"),
                "suggestions": evaluation.get("suggestions"),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: evaluation failed\n{exc}"


def run_all_test_topics(extra_inputs: dict | None = None) -> str:
    """Run and evaluate every topic in test_topics.yaml that matches the workspace's pipeline."""
    try:
        if CONTENT_ROOT is None:
            return "error: no workspace active"
        workspace_format = workspace_module.load_manifest(CONTENT_ROOT)["format"]
        config = yaml.safe_load(TEST_TOPICS_PATH.read_text(encoding="utf-8"))
        summary: dict[str, Any] = {}
        for topic in config.get("topics", []):
            if topic["format"] != workspace_format:
                continue
            run_id = run_pipeline(topic["topic"], topic["format"], extra_inputs)
            if run_id.startswith("error:"):
                summary[topic["id"]] = {"error": run_id}
                continue
            evaluation = run_evaluation(run_id)
            if evaluation.startswith("error:"):
                summary[topic["id"]] = {"run_id": run_id, "error": evaluation}
                continue
            summary[topic["id"]] = json.loads(evaluation)
        return json.dumps(summary, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def next_experiment_path() -> Path:
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    existing = [p for p in EXPERIMENTS_DIR.glob("exp_*.json") if re.fullmatch(r"exp_\d{3}\.json", p.name)]
    return EXPERIMENTS_DIR / f"exp_{len(existing) + 1:03d}.json"


def log_experiment(
    name: str,
    hypothesis: str,
    changes_made: list,
    results: dict,
    conclusion: str,
) -> str:
    """Write an experiment log entry (agent-local scratch)."""
    try:
        path = next_experiment_path()
        payload = {
            "name": name,
            "timestamp": utc_now(),
            "hypothesis": hypothesis,
            "changes_made": changes_made,
            "results": results,
            "conclusion": conclusion,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path.relative_to(ROOT))
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def revert_file(stage_id: str, run_id: str) -> str:
    """Restore a stage's workspace prompt to the text a specific backend run used."""
    try:
        if CONTENT_ROOT is None:
            return "error: no workspace active"
        return workspace_module.restore_prompt_from_run(CONTENT_ROOT, stage_id, run_id)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def diff_against_source(stage_id: str) -> str:
    """Diff a stage's workspace prompt against the backend's current prompt."""
    try:
        if CONTENT_ROOT is None:
            return "error: no workspace active"
        return workspace_module.diff_against_source(CONTENT_ROOT, stage_id)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def promote_prompt(stage_id: str) -> str:
    """Save a stage's edited workspace prompt to the backend's pipeline."""
    if not PROMOTE_ENABLED:
        return (
            "error: promotion is disabled for this run; rerun the agent with --allow-promote "
            "to save changes to the backend pipeline. Your edit still exists in the workspace."
        )
    try:
        if CONTENT_ROOT is None:
            return "error: no workspace active"
        return workspace_module.promote_prompt(CONTENT_ROOT, stage_id)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


TOOLS: dict[str, Callable[..., str]] = {
    "read_file": read_file,
    "write_file": write_file,
    "edit_file": edit_file,
    "list_runs": list_runs,
    "read_run": read_run,
    "read_run_full": read_run_full,
    "diff_files": diff_files,
    "diff_runs": diff_runs,
    "diff_against_source": diff_against_source,
    "run_pipeline": run_pipeline,
    "run_evaluation": run_evaluation,
    "run_all_test_topics": run_all_test_topics,
    "log_experiment": log_experiment,
    "revert_file": revert_file,
    "promote_prompt": promote_prompt,
}


def object_schema(
    properties: dict[str, Any] | None = None,
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "reasoning": {
                "type": "string",
                "description": "Briefly explain why this tool call is the next best step.",
            },
            **(properties or {}),
        },
        "required": required or [],
    }


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="read_file",
        description="Read a file under your workspace root (e.g. prompts/<stage_id>.md).",
        parameters=object_schema({"path": {"type": "string"}}, ["path"]),
    ),
    ToolSpec(
        name="write_file",
        description="Write complete file contents under your workspace root. Use only to create a new file; for edits to an existing file use edit_file instead.",
        parameters=object_schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
    ),
    ToolSpec(
        name="edit_file",
        description=(
            "Replace one exact text segment in an existing file with new text (paragraph-level edit). "
            "old_text must match the file content exactly, including whitespace, and must be unique unless replace_all is true. "
            "Prefer this over write_file for any change to an existing file."
        ),
        parameters=object_schema(
            {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            ["path", "old_text", "new_text"],
        ),
    ),
    ToolSpec(
        name="list_runs",
        description="List the latest backend runs with their evaluation scores.",
        parameters=object_schema(),
    ),
    ToolSpec(
        name="read_run",
        description="Read manifest, evaluation, and script for a run.",
        parameters=object_schema({"run_id": {"type": "string"}}, ["run_id"]),
    ),
    ToolSpec(
        name="read_run_full",
        description="Read all major artifacts for a run.",
        parameters=object_schema({"run_id": {"type": "string"}}, ["run_id"]),
    ),
    ToolSpec(
        name="diff_files",
        description="Return a unified diff between two files in your workspace.",
        parameters=object_schema({"path_a": {"type": "string"}, "path_b": {"type": "string"}}, ["path_a", "path_b"]),
    ),
    ToolSpec(
        name="diff_runs",
        description="Diff a specific stage artifact between two runs.",
        parameters=object_schema(
            {
                "run_id_a": {"type": "string"},
                "run_id_b": {"type": "string"},
                "stage": {"type": "string", "enum": ["script", "outline", "blueprint", "research"]},
            },
            ["run_id_a", "run_id_b"],
        ),
    ),
    ToolSpec(
        name="diff_against_source",
        description=(
            "Diff a stage's workspace prompt (your edits) against the backend pipeline's current prompt "
            "text. Use this before promote_prompt to confirm exactly what will change."
        ),
        parameters=object_schema({"stage_id": {"type": "string"}}, ["stage_id"]),
    ),
    ToolSpec(
        name="promote_prompt",
        description=(
            "Save a stage's edited workspace prompt to the backend's stored pipeline, replacing that "
            "stage's prompt text. This is the ONLY tool that changes the backend's pipeline — "
            "everything else (read_file/write_file/edit_file, run_pipeline) only uses your private "
            "workspace copy. May be disabled for this run, in which case it returns an error "
            "explaining that promotion needs --allow-promote."
        ),
        parameters=object_schema({"stage_id": {"type": "string"}}, ["stage_id"]),
    ),
    ToolSpec(
        name="run_pipeline",
        description=(
            "Run your workspace's edited pipeline on the backend for a topic; format must be the "
            "pipeline you are working on. Returns the new run_id."
        ),
        parameters=object_schema(
            {
                "topic": {"type": "string"},
                "format": {"type": "string"},
                "extra_inputs": {"type": "object"},
            },
            ["topic", "format"],
        ),
    ),
    ToolSpec(
        name="run_evaluation",
        description="Score a completed run with the backend's LLM judge (rubric podcast_quality).",
        parameters=object_schema({"run_id": {"type": "string"}}, ["run_id"]),
    ),
    ToolSpec(
        name="run_all_test_topics",
        description="Run and evaluate every test topic (test_topics.yaml) that matches your pipeline.",
        parameters=object_schema({"extra_inputs": {"type": "object"}}),
    ),
    ToolSpec(
        name="log_experiment",
        description="Write an experiment log entry.",
        parameters=object_schema(
            {
                "name": {"type": "string"},
                "hypothesis": {"type": "string"},
                "changes_made": {"type": "array", "items": {"type": "string"}},
                "results": {"type": "object"},
                "conclusion": {"type": "string"},
            },
            ["name", "hypothesis", "changes_made", "results", "conclusion"],
        ),
    ),
    ToolSpec(
        name="revert_file",
        description="Restore a stage's workspace prompt to the text that a specific earlier run used.",
        parameters=object_schema({"stage_id": {"type": "string"}, "run_id": {"type": "string"}}, ["stage_id", "run_id"]),
    ),
    ToolSpec(
        name="finish_iteration",
        description="Finish the current iteration once there is a clear conclusion.",
        parameters=object_schema({"conclusion": {"type": "string"}}, ["conclusion"]),
    ),
]

READ_ONLY_TOOL_SPECS = [
    tool
    for tool in TOOL_SPECS
    if tool.name in {"read_file", "list_runs", "read_run", "read_run_full", "diff_files", "diff_runs", "diff_against_source"}
]
