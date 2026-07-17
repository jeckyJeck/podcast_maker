from __future__ import annotations

import argparse
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
    from .agent_llm import AgentLLM, ToolCall, ToolSpec, build_agent_llm, PROVIDERS
except ImportError:  # pragma: no cover - supports direct script execution
    from agent_llm import AgentLLM, ToolCall, ToolSpec, build_agent_llm, PROVIDERS

try:
    from rich.console import Console
except ImportError:  # pragma: no cover - optional dependency
    Console = None


ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
EXPERIMENTS_DIR = ROOT / "experiments"
SYSTEM_PROMPT_PATH = ROOT / "agent_system_prompt.md"
console = Console() if Console else None


def log_print(message: str) -> None:
    if console:
        console.print(message)
    else:
        print(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_path(path: str) -> Path:
    candidate = (ROOT / path).resolve()
    if ROOT not in candidate.parents and candidate != ROOT:
        raise ValueError(f"Path escapes optimization_agent root: {path}")
    return candidate


def read_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def read_file(path: str) -> str:
    """Read a file and return its contents as a string."""
    try:
        file_path = safe_path(path)
        if not file_path.exists():
            return f"error: file does not exist: {path}"
        return file_path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - tool boundary
        return f"error: {exc}"


def write_file(path: str, content: str) -> str:
    """Write content to a file, creating it if it does not exist."""
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
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


TOOLS: dict[str, Callable[..., str]] = {
    "read_file": read_file,
    "write_file": write_file,
    "list_runs": list_runs,
    "read_run": read_run,
    "read_run_full": read_run_full,
    "diff_files": diff_files,
    "diff_runs": diff_runs,
    "run_pipeline": run_pipeline,
    "run_evaluation": run_evaluation,
    "run_all_test_topics": run_all_test_topics,
    "log_experiment": log_experiment,
    "revert_file": revert_file,
}


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


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
        description="Write complete file contents under the optimization_agent root.",
        parameters=object_schema({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"]),
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
    if tool.name in {"read_file", "list_runs", "read_run", "read_run_full", "diff_files", "diff_runs"}
]


def summarize_pipeline(format_filter: str | None = None) -> str:
    paths = sorted((ROOT / "pipeline").glob("*.yaml"))
    summaries: list[dict[str, Any]] = []
    for path in paths:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if format_filter and data.get("format") != format_filter:
            continue
        summaries.append(
            {
                "file": str(path.relative_to(ROOT)),
                "format": data.get("format"),
                "stages": [
                    {
                        "id": stage.get("id"),
                        "execution": stage.get("execution"),
                        "prompt": stage.get("prompt"),
                    }
                    for stage in data.get("stages", [])
                ],
            }
        )
    return json.dumps(summaries, ensure_ascii=False, indent=2)


def last_experiments() -> str:
    logs = sorted(EXPERIMENTS_DIR.glob("exp_*.json"))[-5:]
    data = [read_json_if_exists(path) for path in logs]
    return json.dumps(data, ensure_ascii=False, indent=2)


def scores_table() -> str:
    rows = []
    for run_dir in sorted(RUNS_DIR.glob("run_*")):
        manifest = read_json_if_exists(run_dir / "manifest.json") or {}
        evaluation = read_json_if_exists(run_dir / "evaluation.json") or {}
        user = manifest.get("user_inputs", {})
        rows.append(
            {
                "run_id": run_dir.name,
                "topic": user.get("topic"),
                "format": user.get("format"),
                "status": manifest.get("overall_status"),
                "score": evaluation.get("overall_score"),
                "dimensions": evaluation.get("dimension_scores"),
            }
        )
    return json.dumps(rows[-30:], ensure_ascii=False, indent=2)


def compact(text: str, limit: int = 12000) -> str:
    if len(text) <= limit:
        return text
    return text[: limit // 2] + "\n... truncated ...\n" + text[-limit // 2 :]


def preview(value: Any, limit: int = 1200) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, indent=2) if isinstance(value, (dict, list)) else str(value)
    except Exception:  # noqa: BLE001 - defensive logging helper
        text = str(value)
    return compact(text, limit)


def build_context(format_filter: str | None, last_tool: dict[str, Any] | None) -> str:
    context = "\n\n".join(
        [
            "## Pipeline Summary",
            summarize_pipeline(format_filter),
            "## Last 5 Experiments",
            last_experiments(),
            "## Evaluation Scores",
            scores_table(),
            "## Last Tool Result",
            json.dumps(last_tool or {}, ensure_ascii=False, indent=2),
        ]
    )
    return compact(context)


def extract_action(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    data = json.loads(stripped)
    if not isinstance(data, dict):
        raise ValueError("Agent response was not a JSON object")
    for key in ["reasoning", "action", "params", "done"]:
        if key not in data:
            raise ValueError(f"Agent response missing key: {key}")
    if not isinstance(data["params"], dict):
        raise ValueError("Agent params must be an object")
    return data


def action_from_tool_call(tool_call: ToolCall) -> dict[str, Any]:
    params = dict(tool_call.arguments)
    reasoning = str(params.pop("reasoning", "") or "")
    if tool_call.name == "finish_iteration":
        conclusion = str(params.get("conclusion") or reasoning or "Iteration complete.")
        return {"reasoning": conclusion, "action": tool_call.name, "params": {}, "done": True}
    return {
        "reasoning": reasoning or f"Calling {tool_call.name}.",
        "action": tool_call.name,
        "params": params,
        "done": False,
    }


def ask_agent(
    agent_llm: AgentLLM,
    context: str,
    stream_thoughts: bool = False,
    tools: list[ToolSpec] | None = None,
) -> dict[str, Any]:
    response = agent_llm.complete(
        load_system_prompt(),
        context,
        tools=tools or TOOL_SPECS,
        stream_thoughts=stream_thoughts,
    )
    if response.tool_call:
        return action_from_tool_call(response.tool_call)

    response_text = response.text
    try:
        return extract_action(response_text)
    except ValueError as exc:
        log_print(f"Failed to parse agent response: {exc}\nResponse text was:\n{preview(response_text)}")
        return ask_agent(
            agent_llm,
            f"{context}\n\n## LLM response that caused error:\n{preview(response_text)}\n\n## Error was:\n{exc}\n\nPlease fix the JSON formatting and try again.",
            stream_thoughts=stream_thoughts,
            tools=tools,
        )


def run_agent(
    max_iterations: int,
    max_steps: int,
    format_filter: str | None,
    agent_llm: AgentLLM,
    trace: bool = False,
    stream_thoughts: bool = False,
) -> None:
    log_print(f"Using {agent_llm.provider_name} agent model: {agent_llm.model_name}")
    for iteration in range(1, max_iterations + 1):
        log_print(f"Starting agent iteration {iteration}")
        last_tool: dict[str, Any] | None = None
        changes_made: list[str] = []
        hypothesis = ""
        results: dict[str, Any] = {}
        for step in range(1, max_steps + 1):
            log_print(f"Iteration {iteration} step {step}/{max_steps}: requesting next action")
            context = build_context(format_filter, last_tool)
            if trace and last_tool is not None:
                log_print(f"Iteration {iteration} step {step}: last tool result preview:\n{preview(last_tool)}")
            action = ask_agent(agent_llm, context, stream_thoughts=stream_thoughts)
            reasoning = str(action["reasoning"])
            if not hypothesis:
                hypothesis = reasoning
            log_print(
                f"Iteration {iteration} step {step}: model chose action={action['action']} done={bool(action.get('done'))}"
            )
            if trace:
                log_print(f"Iteration {iteration} step {step}: reasoning:\n{preview(reasoning)}")
            if action.get("done"):
                path = log_experiment(
                    name=f"iteration_{iteration:03d}",
                    hypothesis=hypothesis,
                    changes_made=changes_made,
                    results=results,
                    conclusion=reasoning,
                )
                log_print(f"Logged {path}")
                break
            tool_name = action["action"]
            if tool_name not in TOOLS:
                last_tool = {"error": f"unknown action: {tool_name}", "reasoning": reasoning}
                log_print(f"Iteration {iteration} step {step}: unknown action {tool_name}")
                continue
            log_print(f"Iteration {iteration} step {step}: running tool {tool_name}")
            if trace and action["params"]:
                log_print(f"Iteration {iteration} step {step}: tool params:\n{preview(action['params'])}")
            result = TOOLS[tool_name](**action["params"])
            log_print(f"Iteration {iteration} step {step}: tool {tool_name} finished")
            if trace:
                log_print(f"Iteration {iteration} step {step}: tool result:\n{preview(result)}")
            if tool_name in {"write_file", "revert_file"} and result == "ok":
                path = action["params"].get("path")
                if path:
                    changes_made.append(path)
            if tool_name in {"run_evaluation", "run_all_test_topics"} and not result.startswith("error:"):
                results[f"step_{step}"] = result
            last_tool = {
                "step": step,
                "reasoning": reasoning,
                "action": tool_name,
                "params": action["params"],
                "result": result,
            }
        else:
            path = log_experiment(
                name=f"iteration_{iteration:03d}",
                hypothesis=hypothesis,
                changes_made=changes_made,
                results=results,
                conclusion="Reached max steps before done.",
            )
            log_print(f"Logged {path}")


def run_smoke_test(format_filter: str | None, agent_llm: AgentLLM, stream_thoughts: bool = False) -> None:
    """Run a minimal, read-only agent smoke test."""
    log_print("Running smoke test")
    log_print(f"Using {agent_llm.provider_name} agent model: {agent_llm.model_name}")
    log_print("Pipeline summary:")
    log_print(summarize_pipeline(format_filter))
    log_print("Recent runs:")
    log_print(list_runs())

    action = ask_agent(
        agent_llm,
        """
Run exactly one safe tool call for a smoke test. Choose one of the available read-only tools:
- read_file
- list_runs
- read_run
- read_run_full
- diff_files
- diff_runs
""".strip(),
        stream_thoughts=stream_thoughts,
        tools=READ_ONLY_TOOL_SPECS,
    )
    tool_name = action["action"]
    if tool_name not in TOOLS:
        raise RuntimeError(f"Smoke test requested unknown tool: {tool_name}")
    result = TOOLS[tool_name](**action["params"])
    log_print(json.dumps({"action": tool_name, "result": result}, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Autonomous podcast pipeline improvement agent")
    parser.add_argument("--max-iterations", type=int, default=5)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--format")
    parser.add_argument(
        "--agent-provider",
        choices=PROVIDERS,
        help="Agent model provider. Defaults to AGENT_PROVIDER or ollama.",
    )
    parser.add_argument("--agent-model", help="Agent model name. Defaults depend on the provider.")
    parser.add_argument("--smoke-test", action="store_true", help="Run a minimal read-only agent test")
    parser.add_argument("--trace", action="store_true", help="Print reasoning, params, and tool results while running")
    parser.add_argument(
        "--stream-thoughts",
        action="store_true",
        help="For Ollama only: print the model response tokens as they are generated",
    )
    args = parser.parse_args(argv)
    try:
        agent_llm = build_agent_llm(args.agent_provider, args.agent_model)
        if args.smoke_test:
            run_smoke_test(args.format, agent_llm, stream_thoughts=args.stream_thoughts)
            return 0
        run_agent(
            args.max_iterations,
            args.max_steps,
            args.format,
            agent_llm,
            trace=args.trace,
            stream_thoughts=args.stream_thoughts,
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        log_print(f"Agent failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
