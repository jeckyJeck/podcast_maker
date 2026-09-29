"""Generic pipeline executor: interprets validated PIPELINE_CONTRACT.md YAML and
actually runs it against an LLMProvider. Ported from prompts_lab/optimization_agent/engine.py
and reconciled to the real contract (bindings, inputs.*, prompt.source: template, tools).

Note: per-stage `model` overrides are accepted (validated) but not yet applied — the
active provider/model is process-wide (GeminiAdapter is a singleton; see project decisions
on not touching that pattern in this pass).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Callable

from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema import validate as jsonschema_validate

from podcast_maker.engine import sources
from podcast_maker.engine import tools as tools_module
from podcast_maker.services import prompt_template_store
from podcast_maker.services.llm_provider_factory import build_llm_provider

JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*")


class PipelineExecutionError(RuntimeError):
    """Raised for a single stage/attempt failure inside run_with_retries."""


class PipelineRunFailure(RuntimeError):
    """Raised when a pipeline run fails partway through. Carries whatever
    stage_results/outputs were completed before the failure, so callers can
    still persist a manifest for the partial run."""

    def __init__(self, message: str, stage_results: dict[str, Any], outputs: dict[str, Any]):
        super().__init__(message)
        self.stage_results = stage_results
        self.outputs = outputs


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = JSON_FENCE_RE.sub("", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        first_obj = stripped.find("{")
        last_obj = stripped.rfind("}")
        if first_obj != -1 and last_obj != -1 and last_obj > first_obj:
            return json.loads(stripped[first_obj : last_obj + 1])
        first_arr = stripped.find("[")
        last_arr = stripped.rfind("]")
        if first_arr != -1 and last_arr != -1 and last_arr > first_arr:
            return json.loads(stripped[first_arr : last_arr + 1])
        raise


def resolve_prompt_source(stage: dict[str, Any], root: Path, user_id: str) -> str:
    prompt_spec = stage.get("prompt") or {}
    source = prompt_spec.get("source")
    if source == "inline":
        return prompt_spec["text"]
    if source == "file":
        return read_text(root / prompt_spec["path"])
    if source == "template":
        row = prompt_template_store.get_template(user_id, prompt_spec["template_id"])
        return row["prompt_text"]
    raise PipelineExecutionError(f"stage {stage.get('id')}: unsupported prompt source {source!r}")


def _failure_policy(stage: dict[str, Any], defaults: dict[str, Any]) -> dict[str, Any]:
    return stage.get("failure") or (defaults or {}).get("failure") or {}


def _attempts_for(stage: dict[str, Any], defaults: dict[str, Any]) -> int:
    policy = _failure_policy(stage, defaults)
    if policy.get("strategy") == "retry":
        return int(policy.get("max_attempts", 1))
    return 1


def _failure_strategy(stage: dict[str, Any], defaults: dict[str, Any]) -> str:
    return _failure_policy(stage, defaults).get("strategy", "abort")


def run_with_retries(action, stage: dict[str, Any], defaults: dict[str, Any]) -> tuple[Any, int]:
    last_error: Exception | None = None
    max_attempts = _attempts_for(stage, defaults)
    for attempt in range(1, max_attempts + 1):
        try:
            return action(), attempt
        except Exception as exc:  # noqa: BLE001 - stage failure policy decides how to handle it
            last_error = exc
            if attempt == max_attempts:
                break
    raise PipelineExecutionError(str(last_error)) from last_error


def _validate_schema(value: Any, schema_path: str, root: Path) -> None:
    schema = json.loads((root / schema_path).read_text(encoding="utf-8"))
    try:
        jsonschema_validate(instance=value, schema=schema)
    except JSONSchemaValidationError as exc:
        raise PipelineExecutionError(f"response failed schema validation: {exc.message}") from exc


def _extract_response_value(raw_text: str, response_spec: dict[str, Any], root: Path) -> Any:
    if response_spec.get("kind") == "json":
        value = extract_json(raw_text)
        schema_path = response_spec.get("schema")
        if schema_path:
            _validate_schema(value, schema_path, root)
        return value
    return raw_text


def _write_response_value(path: Path, kind: str, value: Any) -> None:
    if kind == "json":
        write_json(path, value)
    else:
        write_text(path, value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2))


def _call_llm(provider, prompt: str, stage: dict[str, Any], metadata: dict[str, Any]) -> str:
    tool_list = tools_module.resolve_tools(stage.get("tools"))
    temperature = stage.get("temperature")
    kwargs = {} if temperature is None else {"temperature": float(temperature)}
    response = provider.generate_text(prompt, tools=tool_list, metadata=metadata, **kwargs)
    return response.text


def _output_value_single(source: str, response_value: Any) -> Any:
    if source == "response":
        return response_value
    if source.startswith("response."):
        field = source.split(".", 1)[1]
        if not isinstance(response_value, dict):
            raise PipelineExecutionError(f"response is not an object; cannot read field {field!r}")
        # Fields aren't necessarily required by the response schema, so a missing
        # field yields None rather than aborting the stage.
        return response_value.get(field)
    raise PipelineExecutionError(f"invalid output source: {source}")


def _aggregate(succeeded: list[tuple[Any, Any]], strategy: str) -> Any:
    if strategy == "concat":
        return "\n\n".join(str(value) for _, value in succeeded)
    if strategy == "concat_with_headers":
        chunks = []
        for index, (item, value) in enumerate(succeeded, start=1):
            if isinstance(item, dict):
                header = item.get("segment_name") or item.get("scene_title") or item.get("title") or index
            else:
                header = index
            chunks.append(f"## {header}\n\n{value}")
        return "\n\n".join(chunks)
    if strategy == "structured_json":
        return [{"item": item, "output": value} for item, value in succeeded]
    raise PipelineExecutionError(f"unknown aggregate strategy: {strategy}")


def _execute_single(
    stage: dict[str, Any],
    context: dict[str, Any],
    run_dir: Path,
    root: Path,
    user_id: str,
    defaults: dict[str, Any],
    provider,
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_id = stage["id"]
    prompt_text = resolve_prompt_source(stage, root, user_id)
    rendered = sources.render_bindings(prompt_text, stage.get("bindings"), context)
    response_spec = stage["response"]

    def call() -> Any:
        raw = _call_llm(provider, rendered, stage, metadata={"stage": stage_id})
        return _extract_response_value(raw, response_spec, root)

    response_value, attempts = run_with_retries(call, stage, defaults)

    file_rel = response_spec["file"]
    _write_response_value(run_dir / file_rel, response_spec.get("kind", "text"), response_value)

    outputs = {
        name: _output_value_single(spec["source"], response_value) for name, spec in stage["outputs"].items()
    }
    stage_result = {"status": "ok", "attempts": attempts, "output_files": [str(file_rel)]}
    return outputs, stage_result


def _execute_map(
    stage: dict[str, Any],
    context: dict[str, Any],
    run_dir: Path,
    root: Path,
    user_id: str,
    defaults: dict[str, Any],
    provider,
    with_context: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_id = stage["id"]
    map_spec = stage["map"]
    items = sources.resolve_source(map_spec["over"], context)
    if not isinstance(items, list):
        raise PipelineExecutionError(f"stage {stage_id}: map.over did not resolve to a list")

    response_spec = stage["response"]
    prompt_text = resolve_prompt_source(stage, root, user_id)
    context_name = map_spec.get("context_name")

    accumulated_text = ""
    succeeded: list[tuple[Any, Any]] = []
    failed = 0
    total_attempts = 0
    output_files: list[str] = []

    for item in items:
        item_context = dict(context)
        item_context["item"] = item
        if with_context:
            item_context["context"] = {context_name: accumulated_text}

        def call() -> Any:
            rendered = sources.render_bindings(prompt_text, stage.get("bindings"), item_context)
            raw = _call_llm(provider, rendered, stage, metadata={"stage": stage_id})
            return _extract_response_value(raw, response_spec, root)

        try:
            response_value, attempts = run_with_retries(call, stage, defaults)
            total_attempts += attempts
        except Exception:
            failed += 1
            if _failure_strategy(stage, defaults) == "skip":
                continue
            raise

        if response_spec.get("per_item_file"):
            file_name = sources.render_file_pattern(response_spec["per_item_file"], item_context)
            _write_response_value(run_dir / file_name, response_spec.get("kind", "text"), response_value)
            output_files.append(file_name)

        succeeded.append((item, response_value))
        if with_context:
            accumulated_text = _aggregate(succeeded, "concat")

    aggregate_value = _aggregate(succeeded, response_spec.get("aggregate_strategy", "concat"))
    if response_spec.get("aggregate_file"):
        aggregate_file = response_spec["aggregate_file"]
        _write_response_value(run_dir / aggregate_file, response_spec.get("kind", "text"), aggregate_value)
        output_files.append(aggregate_file)

    stage_outputs_bucket = {"items": [value for _, value in succeeded], "aggregate": aggregate_value}
    outputs: dict[str, Any] = {}
    for name, spec in stage["outputs"].items():
        source = spec["source"]
        if source == "response.items":
            outputs[name] = stage_outputs_bucket["items"]
        elif source == "response.aggregate":
            outputs[name] = stage_outputs_bucket["aggregate"]
        else:
            raise PipelineExecutionError(f"invalid map output source: {source}")

    stage_result = {
        "status": "ok",
        "attempts": total_attempts,
        "items_total": len(items),
        "items_succeeded": len(succeeded),
        "items_failed": failed,
        "output_files": output_files,
    }
    return outputs, stage_result


def run_pipeline(
    pipeline_data: dict[str, Any],
    inputs: dict[str, Any],
    root: Path,
    run_dir: Path,
    user_id: str,
    run_stages: set[str] | None = None,
    mock_outputs: dict[str, dict[str, Any]] | None = None,
    on_stage_complete: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Executes a validated pipeline. Returns {"outputs": {...}, "stage_results": {...}}.

    on_stage_complete(stage_id, outputs, stage_result), if given, is called right after
    each executed stage succeeds (its response files are already in run_dir), so callers
    can persist progress incrementally. It is not called for stages skipped via run_stages.

    Stages not in run_stages are not executed; their context bucket is seeded from
    mock_outputs[stage_id] (an {output_name: value} dict, same shape execution would
    have produced) so later stages can still reference them.
    """
    mock_outputs = mock_outputs or {}
    defaults = pipeline_data.get("defaults") or {}
    stages = pipeline_data["stages"]
    run_stage_ids = run_stages if run_stages is not None else {s["id"] for s in stages}

    provider = build_llm_provider((defaults.get("model") or {}).get("provider", "gemini"))

    context: dict[str, Any] = {"inputs": inputs}
    stage_results: dict[str, Any] = {}
    executed_outputs: dict[str, dict[str, Any]] = {}

    for stage in stages:
        stage_id = stage["id"]
        execution = stage["execution"]

        if stage_id not in run_stage_ids:
            context[stage_id] = mock_outputs.get(stage_id, {})
            continue

        started = time.perf_counter()
        try:
            if execution == "loop_until":
                raise NotImplementedError("loop_until stages are not implemented yet")
            if execution == "single":
                outputs, result = _execute_single(stage, context, run_dir, root, user_id, defaults, provider)
            elif execution in {"map", "map_with_context"}:
                outputs, result = _execute_map(
                    stage, context, run_dir, root, user_id, defaults, provider,
                    with_context=execution == "map_with_context",
                )
            else:
                raise PipelineExecutionError(f"unknown execution type for stage {stage_id}: {execution}")
        except Exception as exc:
            raise PipelineRunFailure(
                f"stage {stage_id!r} failed: {exc}", stage_results, executed_outputs
            ) from exc

        result["duration_ms"] = int((time.perf_counter() - started) * 1000)
        stage_results[stage_id] = result
        context[stage_id] = outputs
        executed_outputs[stage_id] = outputs
        if on_stage_complete:
            on_stage_complete(stage_id, outputs, result)

    return {"outputs": executed_outputs, "stage_results": stage_results}
