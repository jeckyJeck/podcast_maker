from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

import yaml

try:
    from .agent_llm import AgentLLM, ToolCall, ToolSpec, build_agent_llm, PROVIDERS
    from . import tools as tools_module
    from . import workspace as workspace_module
    from .tools import (
        EXPERIMENTS_DIR,
        READ_ONLY_TOOL_SPECS,
        ROOT,
        TOOL_SPECS,
        TOOLS,
        list_runs,
        log_experiment,
        read_json_if_exists,
        run_summaries,
    )
    from .workspace import WorkspaceInfo
except ImportError:  # pragma: no cover - supports direct script execution
    from agent_llm import AgentLLM, ToolCall, ToolSpec, build_agent_llm, PROVIDERS
    import tools as tools_module
    import workspace as workspace_module
    from tools import (
        EXPERIMENTS_DIR,
        READ_ONLY_TOOL_SPECS,
        ROOT,
        TOOL_SPECS,
        TOOLS,
        list_runs,
        log_experiment,
        read_json_if_exists,
        run_summaries,
    )
    from workspace import WorkspaceInfo

try:
    from rich.console import Console
except ImportError:  # pragma: no cover - optional dependency
    Console = None


SYSTEM_PROMPT_PATH = ROOT / "agent_system_prompt.md"
console = Console() if Console else None


def log_print(message: str) -> None:
    if console:
        try:
            console.print(message)
            return
        except UnicodeEncodeError:
            pass  # fall through to the encoding-safe path below
    encoding = sys.stdout.encoding or "utf-8"
    print(str(message).encode(encoding, errors="replace").decode(encoding, errors="replace"))


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def describe_tools(tool_specs: list[ToolSpec]) -> str:
    """Render tool name + description pairs so smaller models get plain-text guidance
    alongside the function-calling schema (which they may follow less reliably)."""
    lines = [f"- {tool.name}: {tool.description}" for tool in tool_specs]
    return "\n".join(lines)


def stage_output_files(pipeline_data: dict[str, Any]) -> dict[str, str]:
    """{stage_id: run-relative output file} read straight from the pipeline YAML."""
    files: dict[str, str] = {}
    for stage in pipeline_data.get("stages") or []:
        response = stage.get("response") or {}
        file_name = response.get("file") if stage.get("execution") == "single" else response.get("aggregate_file")
        if stage.get("id") and file_name:
            files[stage["id"]] = file_name
    return files


def describe_pipeline(workspace_info: WorkspaceInfo) -> str:
    """Describe the real pipeline this run is improving: every stage's current prompt
    text, read live from the sandboxed workspace copy (never from the backend
    directly, so the model always sees exactly what it's allowed to edit)."""
    manifest = json.loads((workspace_info.root / "manifest.json").read_text(encoding="utf-8"))
    sections = [f"Format: {workspace_info.format}", f"Source: backend pipeline {manifest['pipeline_id']!r} at {manifest['backend_url']} (read-only; edit via the workspace)"]
    # Inputs and stage ids/outputs are defined by the pipeline YAML itself; surface them so the model never guesses.
    pipeline_data = yaml.safe_load((workspace_info.root / "pipeline.yaml").read_text(encoding="utf-8")) or {}
    input_lines = [
        f"- {name} (type: {spec.get('type', 'text')}, "
        + ("required" if spec.get("required") else f"default: {spec.get('default')!r}")
        + ")"
        for name, spec in (pipeline_data.get("inputs") or {}).items()
    ]
    sections.append("Pipeline inputs (pass these as `inputs` to run_pipeline):\n" + ("\n".join(input_lines) or "(none)"))
    sections.append(
        "Stage output files: "
        + ", ".join(f"{stage}: {file}" for stage, file in stage_output_files(pipeline_data).items())
    )
    for stage_id, entry in manifest.get("stages", {}).items():
        prompt_path = workspace_info.root / entry["workspace_file"]
        prompt_text = prompt_path.read_text(encoding="utf-8") if prompt_path.exists() else "(missing)"
        sections.append(
            f"### Stage: {stage_id} (execution: {entry.get('execution')}, workspace file: {entry['workspace_file']})\n"
            f"{prompt_text}"
        )
    return "\n\n".join(sections)


def last_experiments() -> str:
    logs = sorted(EXPERIMENTS_DIR.glob("exp_*.json"))[-5:]
    data = [read_json_if_exists(path) for path in logs]
    return json.dumps(data, ensure_ascii=False, indent=2)


def scores_table() -> str:
    try:
        rows = run_summaries()
    except Exception as exc:  # noqa: BLE001 - backend may be unreachable; don't kill the context build
        return f"(could not fetch runs from the backend: {exc})"
    return json.dumps(rows, ensure_ascii=False, indent=2)


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


def build_context(
    workspace_info: WorkspaceInfo,
    last_tool: dict[str, Any] | None,
    task: str | None = None,
    tool_specs: list[ToolSpec] | None = None,
) -> str:
    """Four ordered sections: tools, the pipeline being improved (+ supporting
    context), the human's specific objective, then the running loop's last result.
    Section 1 (general role) lives in agent_system_prompt.md, not here."""
    sections = [
        "## Available Tools",
        describe_tools(tool_specs or TOOL_SPECS),
        "## Pipeline You Are Improving",
        describe_pipeline(workspace_info),
        "## Recent Experiments",
        last_experiments(),
        "## Evaluation Scores",
        scores_table(),
    ]
    if task:
        sections.extend(["## Current Objective (from human operator)", task])
    sections.extend(
        [
            "## Last Tool Result",
            json.dumps(last_tool or {}, ensure_ascii=False, indent=2),
        ]
    )
    # Higher limit than the default compact() budget: real stage prompts (e.g. the
    # scriptwriter's) run several thousand characters each and need to stay intact.
    return compact("\n\n".join(sections), limit=40000)


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


MAX_ASK_AGENT_RETRIES = 3


def ask_agent(
    agent_llm: AgentLLM,
    context: str,
    stream_thoughts: bool = False,
    tools: list[ToolSpec] | None = None,
    retry_count: int = 0,
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
        if retry_count >= MAX_ASK_AGENT_RETRIES:
            log_print(
                f"ask_agent: giving up after {retry_count} retries — model keeps returning unparseable output. "
                "Treating this step as done with a failure conclusion."
            )
            return {
                "reasoning": f"Could not get a valid action after {retry_count} retries: {exc}",
                "action": "finish_iteration",
                "params": {},
                "done": True,
            }
        log_print(
            f"ask_agent: model response was not a valid action (retry {retry_count + 1}/{MAX_ASK_AGENT_RETRIES}). "
            f"Parse error: {exc}\nResponse text was:\n{preview(response_text)}"
        )
        return ask_agent(
            agent_llm,
            f"{context}\n\n## LLM response that caused error:\n{preview(response_text)}\n\n## Error was:\n{exc}\n\nPlease fix the JSON formatting and try again.",
            stream_thoughts=stream_thoughts,
            tools=tools,
            retry_count=retry_count + 1,
        )


def run_agent(
    max_iterations: int,
    max_steps: int,
    workspace_info: WorkspaceInfo,
    agent_llm: AgentLLM,
    trace: bool = False,
    stream_thoughts: bool = False,
    task: str | None = None,
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
            context = build_context(workspace_info, last_tool, task=task)
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
            if tool_name in {"write_file", "edit_file", "revert_file"} and result == "ok":
                path = action["params"].get("path") or action["params"].get("stage_id")
                if path:
                    changes_made.append(path)
            if tool_name == "promote_prompt" and not result.startswith("error:"):
                stage_id = action["params"].get("stage_id")
                if stage_id:
                    changes_made.append(f"PROMOTED:{stage_id}")
            if tool_name in {"run_evaluation", "run_all_test_cases"} and not result.startswith("error:"):
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


def run_smoke_test(workspace_info: WorkspaceInfo, agent_llm: AgentLLM, stream_thoughts: bool = False) -> None:
    """Run a minimal, read-only agent smoke test."""
    log_print("Running smoke test")
    log_print(f"Using {agent_llm.provider_name} agent model: {agent_llm.model_name}")
    log_print("Pipeline summary:")
    log_print(describe_pipeline(workspace_info))
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
- diff_against_source
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
    parser.add_argument(
        "--format",
        required=True,
        help="Backend pipeline id to work on, e.g. duo_long or solo_short. "
        "Fetches that pipeline from the backend (BACKEND_URL) and extracts its "
        "stage prompts into a fresh sandboxed workspace for this run.",
    )
    parser.add_argument(
        "--allow-promote",
        action="store_true",
        help="Allow the agent to call promote_prompt, saving its workspace edits to the backend's "
        "stored pipeline (POST /prompts-test-api/pipelines/<format>). Off by default — without this flag, "
        "promote_prompt returns an explanatory error and all edits stay confined to the workspace.",
    )
    parser.add_argument(
        "--task",
        help="Specific objective for this run, injected into the agent's context as the current directive. "
        "If omitted, the agent decides what to work on purely from past runs/experiments.",
    )
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
        workspace_info = workspace_module.start_workspace(args.format)
        tools_module.CONTENT_ROOT = workspace_info.root
        tools_module.PROMOTE_ENABLED = args.allow_promote
        log_print(
            f"Workspace {workspace_info.workspace_id} ready at {workspace_info.root} "
            f"(promote {'enabled' if args.allow_promote else 'disabled'})"
        )

        agent_llm = build_agent_llm(args.agent_provider, args.agent_model)
        if args.smoke_test:
            run_smoke_test(workspace_info, agent_llm, stream_thoughts=args.stream_thoughts)
            return 0
        run_agent(
            args.max_iterations,
            args.max_steps,
            workspace_info,
            agent_llm,
            trace=args.trace,
            stream_thoughts=args.stream_thoughts,
            task=args.task,
        )
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        log_print(f"Agent failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
