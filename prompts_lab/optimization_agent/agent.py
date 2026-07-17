from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

import yaml

try:
    from .agent_llm import AgentLLM, ToolCall, ToolSpec, build_agent_llm, PROVIDERS
    from .tools import (
        EXPERIMENTS_DIR,
        READ_ONLY_TOOL_SPECS,
        ROOT,
        RUNS_DIR,
        TOOL_SPECS,
        TOOLS,
        list_runs,
        log_experiment,
        read_json_if_exists,
    )
except ImportError:  # pragma: no cover - supports direct script execution
    from agent_llm import AgentLLM, ToolCall, ToolSpec, build_agent_llm, PROVIDERS
    from tools import (
        EXPERIMENTS_DIR,
        READ_ONLY_TOOL_SPECS,
        ROOT,
        RUNS_DIR,
        TOOL_SPECS,
        TOOLS,
        list_runs,
        log_experiment,
        read_json_if_exists,
    )

try:
    from rich.console import Console
except ImportError:  # pragma: no cover - optional dependency
    Console = None


SYSTEM_PROMPT_PATH = ROOT / "agent_system_prompt.md"
console = Console() if Console else None


def log_print(message: str) -> None:
    if console:
        console.print(message)
    else:
        print(message)


def load_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


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
