from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

try:
    from google import genai
except ImportError:  # pragma: no cover - handled at runtime
    genai = None

try:
    from rich.console import Console
except ImportError:  # pragma: no cover - optional dependency
    Console = None


PIPELINE_MODEL = "gemini-2.5-flash"
ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
REF_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")

console = Console() if Console else None


class PipelineError(Exception):
    pass


@dataclass
class StageOutput:
    name: str
    value: Any
    file: str | None = None


def log_print(message: str) -> None:
    if console:
        console.print(message)
    else:
        print(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise PipelineError(f"YAML file did not contain an object: {path}")
    return data


def json_for_prompt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
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


def get_path(data: Any, parts: list[str]) -> Any:
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            return None
    return current


def resolve_ref(expr: str, context: dict[str, Any]) -> Any:
    parts = expr.split(".")
    if not parts:
        return ""
    root = context.get(parts[0])
    if root is None:
        return ""
    if len(parts) == 1:
        return root
    value = get_path(root, parts[1:])
    return "" if value is None else value


def resolve_template(value: Any, context: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    full = REF_RE.fullmatch(value.strip())
    if full:
        return resolve_ref(full.group(1), context)

    def replace(match: re.Match[str]) -> str:
        return json_for_prompt(resolve_ref(match.group(1), context))

    return REF_RE.sub(replace, value)


def render_prompt(prompt_text: str, inputs: dict[str, Any]) -> str:
    rendered = prompt_text
    for key, value in inputs.items():
        text_value = json_for_prompt(value)
        for token in {key, key.upper()}:
            rendered = rendered.replace(f"{{{{{token}}}}}", text_value)
    return rendered


def safe_filename(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return sanitized.strip("_") or "item"


def render_file_pattern(pattern: str, context: dict[str, Any]) -> str:
    rendered = resolve_template(pattern, context)
    return safe_filename(str(rendered))


def next_run_id() -> str:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    existing = [p for p in RUNS_DIR.iterdir() if p.is_dir() and re.fullmatch(r"run_\d{3}", p.name)]
    return f"run_{len(existing) + 1:03d}"


def validate_required_fields(value: Any, required_fields: list[str]) -> None:
    if not isinstance(value, dict):
        raise PipelineError("Expected JSON object for schema-validated output")
    missing = [field for field in required_fields if field not in value]
    if missing:
        raise PipelineError(f"Missing required JSON fields: {', '.join(missing)}")


def call_gemini(prompt: str, model: str, log_path: Path) -> str:
    if genai is None:
        raise PipelineError("google-genai is not installed. Install requirements.txt first.")
    load_dotenv(ROOT / ".env")
    start = time.perf_counter()
    client = genai.Client()
    response = client.models.generate_content(model=model, contents=prompt)
    text = getattr(response, "text", None)
    if not text:
        raise PipelineError("Gemini returned an empty response")
    duration_ms = int((time.perf_counter() - start) * 1000)
    with log_path.open("a", encoding="utf-8") as log:
        log.write(
            json.dumps(
                {
                    "model": model,
                    "prompt_length": len(prompt),
                    "response_length": len(text),
                    "duration_ms": duration_ms,
                    "timestamp": utc_now(),
                }
            )
            + "\n"
        )
    return text


def output_spec_for_single(stage: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    outputs = stage.get("outputs") or {}
    for name, spec in outputs.items():
        if isinstance(spec, dict) and "file" in spec:
            return name, spec
    raise PipelineError(f"Stage {stage.get('id')} has no file output")


def build_inputs(stage: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {key: resolve_template(value, context) for key, value in (stage.get("inputs") or {}).items()}


def execute_llm_stage(
    stage: dict[str, Any],
    context: dict[str, Any],
    run_dir: Path,
    log_path: Path,
) -> StageOutput:
    prompt_path = ROOT / stage["prompt"]
    prompt = render_prompt(read_text(prompt_path), build_inputs(stage, context))
    raw = call_gemini(prompt, PIPELINE_MODEL, log_path)
    output_name, spec = output_spec_for_single(stage)
    output_path = run_dir / spec["file"]

    if output_path.suffix.lower() == ".json" or spec.get("schema"):
        value = extract_json(raw)
        validate_required_fields(value, spec.get("required_fields", []))
        write_text(output_path, json.dumps(value, ensure_ascii=False, indent=2))
    else:
        value = raw
        write_text(output_path, value)
    return StageOutput(output_name, value, spec["file"])


def aggregate_items(items: list[tuple[Any, str]], strategy: str) -> str:
    if strategy == "concat":
        return "\n\n".join(text for _, text in items)
    if strategy == "concat_with_headers":
        chunks = []
        for index, (item, text) in enumerate(items, start=1):
            if isinstance(item, dict):
                header = item.get("segment_name") or item.get("scene_title") or item.get("title") or index
            else:
                header = index
            chunks.append(f"## {header}\n\n{text}")
        return "\n\n".join(chunks)
    if strategy == "structured_json":
        return json.dumps([{"item": item, "output": text} for item, text in items], ensure_ascii=False, indent=2)
    raise PipelineError(f"Unknown aggregate strategy: {strategy}")


def attempts_for(stage: dict[str, Any]) -> int:
    failure = stage.get("on_failure") or {}
    if failure.get("strategy") == "retry":
        return int(failure.get("max_attempts", 1))
    return 1


def failure_strategy(stage: dict[str, Any]) -> str:
    return (stage.get("on_failure") or {}).get("strategy", "abort")


def run_with_retries(action, stage: dict[str, Any]) -> tuple[Any, int]:
    last_error = None
    max_attempts = attempts_for(stage)
    for attempt in range(1, max_attempts + 1):
        try:
            return action(), attempt
        except Exception as exc:  # noqa: BLE001 - stage policy decides how to handle it
            last_error = exc
            if attempt == max_attempts:
                break
    raise PipelineError(str(last_error))


def execute_map_stage(
    stage: dict[str, Any],
    context: dict[str, Any],
    run_dir: Path,
    log_path: Path,
    with_context: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_id = stage["id"]
    items = resolve_template(stage["over"], context)
    if not isinstance(items, list):
        raise PipelineError(f"Stage {stage_id} expected list from 'over' reference")

    outputs = stage.get("outputs") or {}
    per_item_pattern = outputs.get("per_item")
    aggregate_spec = outputs.get("aggregate") or {}
    if not per_item_pattern or not aggregate_spec:
        raise PipelineError(f"Stage {stage_id} needs per_item and aggregate outputs")

    succeeded: list[tuple[Any, str]] = []
    failed = 0
    total_attempts = 0
    accumulated = ""

    for item in items:
        item_context = dict(context)
        item_context[stage["item_var"]] = item
        if with_context:
            item_context[stage.get("accumulate_var", "previous_items")] = accumulated

        def one_call() -> str:
            prompt_path = ROOT / stage["prompt"]
            prompt = render_prompt(read_text(prompt_path), build_inputs(stage, item_context))
            return call_gemini(prompt, PIPELINE_MODEL, log_path)

        try:
            raw, attempts = run_with_retries(one_call, stage)
            total_attempts += attempts
            file_name = render_file_pattern(per_item_pattern, item_context)
            write_text(run_dir / file_name, raw)
            succeeded.append((item, raw))
            accumulated = aggregate_items(succeeded, "concat")
        except Exception as exc:  # noqa: BLE001 - stage policy decides how to handle it
            failed += 1
            if failure_strategy(stage) == "skip":
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(json.dumps({"stage": stage_id, "skipped_item": item, "error": str(exc)}) + "\n")
                continue
            raise

    aggregate_text = aggregate_items(succeeded, aggregate_spec.get("strategy", "concat"))
    write_text(run_dir / aggregate_spec["file"], aggregate_text)
    stage_context = {"aggregate": aggregate_text}
    return stage_context, {
        "status": "ok",
        "attempts": total_attempts,
        "items_total": len(items),
        "items_succeeded": len(succeeded),
        "items_failed": failed,
    }


def snapshot_inputs(pipeline_path: Path, pipeline: dict[str, Any], run_dir: Path) -> dict[str, str]:
    snapshots = run_dir / "snapshots"
    snapshots.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pipeline_path, snapshots / pipeline_path.name)
    hashes: dict[str, str] = {}
    for stage in pipeline.get("stages", []):
        prompt_path = ROOT / stage["prompt"]
        hashes[stage["id"]] = sha256_file(prompt_path)
        shutil.copy2(prompt_path, snapshots / prompt_path.name)
    return hashes


def parse_cli(argv: list[str]) -> tuple[Path, str | None, dict[str, str]]:
    parser = argparse.ArgumentParser(description="Run a podcast pipeline YAML")
    parser.add_argument("--pipeline", required=True)
    parser.add_argument("--run-id")
    known, unknown = parser.parse_known_args(argv)
    user_inputs: dict[str, str] = {}
    index = 0
    while index < len(unknown):
        key = unknown[index]
        if not key.startswith("--") or index + 1 >= len(unknown):
            raise SystemExit(f"Invalid argument: {key}")
        user_inputs[key[2:].replace("-", "_")] = unknown[index + 1]
        index += 2
    return Path(known.pipeline), known.run_id, user_inputs


def apply_user_defaults(pipeline: dict[str, Any], user_inputs: dict[str, str]) -> dict[str, Any]:
    merged: dict[str, Any] = dict(user_inputs)
    for item in pipeline.get("user_inputs", []):
        key = item["key"]
        if key not in merged and "default" in item:
            merged[key] = item["default"]
        if item.get("required") and key not in merged:
            raise PipelineError(f"Missing required user input: --{key.replace('_', '-')}")
    return merged


def run_pipeline(pipeline_file: str, run_id: str | None, user_inputs: dict[str, str]) -> str:
    pipeline_path = (ROOT / pipeline_file).resolve() if not Path(pipeline_file).is_absolute() else Path(pipeline_file)
    pipeline = load_yaml(pipeline_path)
    user_inputs = apply_user_defaults(pipeline, user_inputs)
    run_id = run_id or next_run_id()
    run_dir = RUNS_DIR / run_id
    if run_dir.exists():
        raise PipelineError(f"Run directory already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    log_path = run_dir / "pipeline.log"

    stage_results: dict[str, Any] = {}
    context: dict[str, Any] = {"user": user_inputs}
    prompt_hashes = snapshot_inputs(pipeline_path, pipeline, run_dir)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "timestamp": utc_now(),
        "pipeline_file": str(pipeline_path.relative_to(ROOT)),
        "pipeline_hash": sha256_file(pipeline_path),
        "prompt_hashes": prompt_hashes,
        "user_inputs": user_inputs,
        "stage_results": stage_results,
        "overall_status": "ok",
    }

    try:
        for stage in pipeline.get("stages", []):
            stage_id = stage["id"]
            execution = stage.get("execution")
            started = time.perf_counter()
            log_print(f"Running stage {stage_id} ({execution})")
            if execution == "loop_until":
                raise NotImplementedError("loop_until stages are parsed but not implemented yet")
            if execution == "single":
                output, attempts = run_with_retries(lambda: execute_llm_stage(stage, context, run_dir, log_path), stage)
                context[stage_id] = {output.name: output.value}
                result = {"status": "ok", "attempts": attempts}
            elif execution in {"map", "map_with_context"}:
                context[stage_id], result = execute_map_stage(
                    stage, context, run_dir, log_path, with_context=execution == "map_with_context"
                )
            else:
                raise PipelineError(f"Unknown execution type for stage {stage_id}: {execution}")
            result["duration_ms"] = int((time.perf_counter() - started) * 1000)
            stage_results[stage_id] = result
    except Exception as exc:  # noqa: BLE001 - manifest must capture any fatal failure
        manifest["overall_status"] = "failed"
        manifest["failure_reason"] = str(exc)
        write_text(run_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        raise

    write_text(run_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return run_id


def main(argv: list[str] | None = None) -> int:
    pipeline_file, run_id, user_inputs = parse_cli(argv or sys.argv[1:])
    try:
        new_run_id = run_pipeline(str(pipeline_file), run_id, user_inputs)
        log_print(f"Completed {new_run_id}")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        log_print(f"Pipeline failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

