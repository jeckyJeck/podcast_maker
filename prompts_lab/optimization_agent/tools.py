from __future__ import annotations

import difflib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

try:
    from .agent_llm import ToolSpec
    from . import workspace as workspace_module
except ImportError:  # pragma: no cover - supports direct script execution
    from agent_llm import ToolSpec
    import workspace as workspace_module


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
EXPERIMENTS_DIR = ROOT / "experiments"

# Set by agent.py at startup once a workspace exists. read_file/write_file/edit_file
# resolve against this instead of ROOT so the agent can never touch files outside its
# sandboxed workspace copy. promote_prompt is the only path back to the real files.
CONTENT_ROOT: Path | None = None
PROMOTE_ENABLED: bool = False


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_path(path: str) -> Path:
    candidate = (ROOT / path).resolve()
    if ROOT not in candidate.parents and candidate != ROOT:
        raise ValueError(f"Path escapes optimization_agent root: {path}")
    return candidate


def safe_content_path(path: str) -> Path:
    """Resolve a path for read_file/write_file/edit_file against the active workspace.

    Confines content edits to CONTENT_ROOT (the sandboxed workspace) so the agent can
    never write to common_resources or anything else outside its own copy.
    """
    base = CONTENT_ROOT or ROOT
    candidate = (base / path).resolve()
    if base not in candidate.parents and candidate != base:
        raise ValueError(f"Path escapes workspace root: {path}")
    return candidate


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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


def list_runs() -> str:
    """Return a JSON list of all run directories with their manifest summaries."""
    entries: list[dict[str, Any]] = []
    for run_dir in sorted(RUNS_DIR.glob("run_*")):
        if not run_dir.is_dir():
            continue
        manifest = read_json_if_exists(run_dir / "manifest.json") or {}
        evaluation = read_json_if_exists(run_dir / "evaluation.json") or {}
        user_inputs = manifest.get("user_inputs", {})
        entries.append(
            {
                "run_id": run_dir.name,
                "timestamp": manifest.get("timestamp"),
                "topic": user_inputs.get("topic"),
                "format": user_inputs.get("format"),
                "overall_status": manifest.get("overall_status"),
                "overall_score": evaluation.get("overall_score"),
            }
        )
    return json.dumps(entries, ensure_ascii=False, indent=2)


def read_run(run_id: str) -> str:
    """Return key contents of a run as a JSON object."""
    try:
        run_dir = safe_path(f"runs/{run_id}")
        data = {
            "manifest": read_json_if_exists(run_dir / "manifest.json"),
            "evaluation": read_json_if_exists(run_dir / "evaluation.json"),
            "script": (run_dir / "script.txt").read_text(encoding="utf-8")
            if (run_dir / "script.txt").exists()
            else None,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def read_run_full(run_id: str) -> str:
    """Return all major contents of a run directory as a JSON object."""
    try:
        run_dir = safe_path(f"runs/{run_id}")
        data = {
            "manifest": read_json_if_exists(run_dir / "manifest.json"),
            "evaluation": read_json_if_exists(run_dir / "evaluation.json"),
            "blueprint": read_json_if_exists(run_dir / "blueprint.json"),
            "research": (run_dir / "research.md").read_text(encoding="utf-8")
            if (run_dir / "research.md").exists()
            else None,
            "outline": read_json_if_exists(run_dir / "outline.json"),
            "script": (run_dir / "script.txt").read_text(encoding="utf-8")
            if (run_dir / "script.txt").exists()
            else None,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def diff_files(path_a: str, path_b: str) -> str:
    """Return a unified diff between two files."""
    try:
        a = safe_path(path_a)
        b = safe_path(path_b)
        text_a = a.read_text(encoding="utf-8").splitlines(keepends=True)
        text_b = b.read_text(encoding="utf-8").splitlines(keepends=True)
        return "".join(difflib.unified_diff(text_a, text_b, fromfile=path_a, tofile=path_b))
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def diff_runs(run_id_a: str, run_id_b: str, stage: str = "script") -> str:
    """Return a diff of a specific output file between two runs."""
    stage_files = {
        "script": "script.txt",
        "outline": "outline.json",
        "blueprint": "blueprint.json",
        "research": "research.md",
    }
    if stage not in stage_files:
        return f"error: unknown stage: {stage}"
    return diff_files(f"runs/{run_id_a}/{stage_files[stage]}", f"runs/{run_id_b}/{stage_files[stage]}")


def pipeline_for_format(format: str) -> str:
    path = ROOT / "pipeline" / f"{format}.yaml"
    if path.exists():
        return f"pipeline/{format}.yaml"
    aliases = {"duo_long": "pipeline/duo_long.yaml", "solo_short": "pipeline/solo_short.yaml"}
    if format in aliases:
        return aliases[format]
    raise ValueError(f"No pipeline YAML found for format: {format}")


def run_subprocess(args: list[str]) -> tuple[int, str]:
    completed = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, check=False)
    output = "\n".join(part for part in [completed.stdout.strip(), completed.stderr.strip()] if part)
    return completed.returncode, output


def newest_run_id_before_after(before: set[str]) -> str | None:
    after = {p.name for p in RUNS_DIR.glob("run_*") if p.is_dir()}
    created = sorted(after - before)
    return created[-1] if created else None


def run_pipeline(topic: str, format: str, extra_inputs: dict | None = None) -> str:
    """Execute the pipeline for a given topic and format by calling engine.py."""
    try:
        before = {p.name for p in RUNS_DIR.glob("run_*") if p.is_dir()}
        args = [
            sys.executable,
            "engine.py",
            "--pipeline",
            pipeline_for_format(format),
            "--topic",
            topic,
            "--format",
            format,
        ]
        for key, value in (extra_inputs or {}).items():
            args.extend([f"--{key.replace('_', '-')}", str(value)])
        code, output = run_subprocess(args)
        if code != 0:
            return f"error: pipeline failed\n{output}"
        return newest_run_id_before_after(before) or output
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def run_evaluation(run_id: str) -> str:
    """Run the LLM evaluator on a completed run and write evaluation.json."""
    code, output = run_subprocess([sys.executable, "evaluator.py", "--run-id", run_id])
    if code != 0:
        return f"error: evaluation failed\n{output}"
    evaluation = read_json_if_exists(ROOT / "runs" / run_id / "evaluation.json")
    if not evaluation:
        return output
    return json.dumps(
        {
            "run_id": run_id,
            "overall_score": evaluation.get("overall_score"),
            "dimension_scores": evaluation.get("dimension_scores"),
        },
        ensure_ascii=False,
        indent=2,
    )


def run_all_test_topics(extra_inputs: dict | None = None) -> str:
    """Run and evaluate every topic in evaluation/test_topics.yaml."""
    try:
        config = yaml.safe_load((ROOT / "evaluation" / "test_topics.yaml").read_text(encoding="utf-8"))
        summary: dict[str, Any] = {}
        for topic in config.get("topics", []):
            run_id = run_pipeline(topic["topic"], topic["format"], extra_inputs)
            if run_id.startswith("error:"):
                summary[topic["id"]] = {"error": run_id}
                continue
            evaluation = run_evaluation(run_id)
            if evaluation.startswith("error:"):
                summary[topic["id"]] = {"run_id": run_id, "error": evaluation}
                continue
            parsed = json.loads(evaluation)
            summary[topic["id"]] = parsed
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
    """Write an experiment log entry."""
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


def revert_file(path: str, run_id: str) -> str:
    """Revert a prompt or pipeline YAML file to the version used in a specific run."""
    try:
        target = safe_path(path)
        snapshot = safe_path(f"runs/{run_id}/snapshots/{Path(path).name}")
        if not snapshot.exists():
            return f"error: snapshot not found for {path} in {run_id}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(snapshot.read_text(encoding="utf-8"), encoding="utf-8")
        return "ok"
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def diff_against_source(stage_id: str) -> str:
    """Diff a stage's workspace prompt against the current real prompt in common_resources."""
    try:
        if CONTENT_ROOT is None:
            return "error: no workspace active"
        return workspace_module.diff_against_source(CONTENT_ROOT, stage_id)
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def promote_prompt(stage_id: str) -> str:
    """Write a stage's edited workspace prompt back into the real common_resources pipeline.yaml."""
    if not PROMOTE_ENABLED:
        return (
            "error: promotion is disabled for this run; rerun the agent with --allow-promote "
            "to apply changes to common_resources. Your edit still exists in the workspace."
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
        description="Read a file under the optimization_agent root.",
        parameters=object_schema({"path": {"type": "string"}}, ["path"]),
    ),
    ToolSpec(
        name="write_file",
        description="Write complete file contents under the optimization_agent root. Use only to create a new file; for edits to an existing file use edit_file instead.",
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
        description="List all run directories with manifest and evaluation summaries.",
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
        description="Return a unified diff between two files.",
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
            "Diff a stage's workspace prompt (your edits) against the current real prompt text in "
            "common_resources. Use this before promote_prompt to confirm exactly what will change."
        ),
        parameters=object_schema({"stage_id": {"type": "string"}}, ["stage_id"]),
    ),
    ToolSpec(
        name="promote_prompt",
        description=(
            "Write a stage's edited workspace prompt back into the real pipeline.yaml under "
            "common_resources, replacing that stage's prompt text. This is the ONLY tool that changes "
            "production files — everything else (read_file/write_file/edit_file) only touches your "
            "private workspace copy. May be disabled for this run, in which case it returns an error "
            "explaining that promotion needs --allow-promote."
        ),
        parameters=object_schema({"stage_id": {"type": "string"}}, ["stage_id"]),
    ),
    ToolSpec(
        name="run_pipeline",
        description="Execute the podcast pipeline for a topic and format.",
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
        description="Run the LLM evaluator on a completed run.",
        parameters=object_schema({"run_id": {"type": "string"}}, ["run_id"]),
    ),
    ToolSpec(
        name="run_all_test_topics",
        description="Run and evaluate every topic in evaluation/test_topics.yaml.",
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
        description="Revert a prompt or pipeline YAML file to the version used in a specific run.",
        parameters=object_schema({"path": {"type": "string"}, "run_id": {"type": "string"}}, ["path", "run_id"]),
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
