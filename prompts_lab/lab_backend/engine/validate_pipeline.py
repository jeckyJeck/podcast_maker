from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - handled at CLI boundary
    yaml = None


ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
VALID_INPUT_TYPES = {"text", "json", "number", "boolean"}
VALID_STAGE_TYPES = {"llm"}
VALID_EXECUTIONS = {"single", "map", "map_with_context"}
VALID_PROMPT_SOURCES = {"file", "inline", "template"}
VALID_BINDING_FORMATS = {"text", "json"}
VALID_RESPONSE_KINDS = {"text", "json"}
VALID_AGGREGATE_STRATEGIES = {"concat", "concat_with_headers", "structured_json"}
VALID_FAILURE_STRATEGIES = {"abort", "retry", "skip"}


@dataclass
class ValidationIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class PipelineValidationError(ValueError):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__("\n".join(str(issue) for issue in issues))


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _is_list(value: Any) -> bool:
    return isinstance(value, list)


def _add(issues: list[ValidationIssue], path: str, message: str) -> None:
    issues.append(ValidationIssue(path, message))


def _validate_id(value: Any, path: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, str) or not value.strip():
        _add(issues, path, "must be a non-empty string")
        return
    if not ID_RE.fullmatch(value):
        _add(issues, path, "must start with a letter and contain only letters, numbers, '_' or '-'")


def _validate_failure(value: Any, path: str, issues: list[ValidationIssue]) -> None:
    if value is None:
        return
    if not _is_mapping(value):
        _add(issues, path, "must be a mapping")
        return
    strategy = value.get("strategy")
    if strategy is not None and strategy not in VALID_FAILURE_STRATEGIES:
        _add(issues, f"{path}.strategy", f"must be one of {sorted(VALID_FAILURE_STRATEGIES)}")
    if "max_attempts" in value:
        max_attempts = value["max_attempts"]
        if not isinstance(max_attempts, int) or max_attempts < 1:
            _add(issues, f"{path}.max_attempts", "must be an integer >= 1")


def _validate_defaults(value: Any, issues: list[ValidationIssue]) -> None:
    if value is None:
        return
    if not _is_mapping(value):
        _add(issues, "defaults", "must be a mapping")
        return
    if "failure" in value:
        _validate_failure(value.get("failure"), "defaults.failure", issues)
    model = value.get("model")
    if model is not None and not _is_mapping(model):
        _add(issues, "defaults.model", "must be a mapping")
    output_contract = value.get("output_contract")
    if output_contract is not None and not _is_mapping(output_contract):
        _add(issues, "defaults.output_contract", "must be a mapping")


def _validate_inputs(value: Any, issues: list[ValidationIssue]) -> set[str]:
    input_names: set[str] = set()
    if not _is_mapping(value):
        _add(issues, "inputs", "must be a mapping")
        return input_names

    for name, spec in value.items():
        path = f"inputs.{name}"
        _validate_id(name, path, issues)
        input_names.add(str(name))
        if not _is_mapping(spec):
            _add(issues, path, "must be a mapping")
            continue
        input_type = spec.get("type")
        if input_type not in VALID_INPUT_TYPES:
            _add(issues, f"{path}.type", f"must be one of {sorted(VALID_INPUT_TYPES)}")
        if "required" in spec and not isinstance(spec["required"], bool):
            _add(issues, f"{path}.required", "must be a boolean")
    return input_names


def _validate_prompt(prompt: Any, stage_path: str, root: Path, issues: list[ValidationIssue]) -> str | None:
    path = f"{stage_path}.prompt"
    if not _is_mapping(prompt):
        _add(issues, path, "must be a mapping")
        return None

    source = prompt.get("source")
    if source not in VALID_PROMPT_SOURCES:
        _add(issues, f"{path}.source", f"must be one of {sorted(VALID_PROMPT_SOURCES)}")
        return None

    if source == "file":
        prompt_path = prompt.get("path")
        if not isinstance(prompt_path, str) or not prompt_path.strip():
            _add(issues, f"{path}.path", "is required for source=file")
            return None
        resolved = root / prompt_path
        if not resolved.exists() or not resolved.is_file():
            _add(issues, f"{path}.path", f"file does not exist relative to root: {prompt_path}")
            return None
        try:
            return resolved.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            _add(issues, f"{path}.path", f"could not read file: {exc}")
            return None

    if source == "inline":
        text = prompt.get("text")
        if not isinstance(text, str) or not text.strip():
            _add(issues, f"{path}.text", "is required for source=inline")
            return None
        return text

    template_id = prompt.get("template_id")
    if not isinstance(template_id, str) or not template_id.strip():
        _add(issues, f"{path}.template_id", "is required for source=template")
    return None


def _source_exists(
    source: str,
    input_names: set[str],
    available_outputs: dict[str, set[str]],
    execution: str,
    context_name: str | None,
) -> bool:
    if source.startswith("inputs."):
        return source.split(".", 1)[1] in input_names
    if source == "item" or source.startswith("item."):
        return execution in {"map", "map_with_context"}
    if source.startswith("context."):
        return execution == "map_with_context" and source.split(".", 1)[1] == context_name
    parts = source.split(".")
    if len(parts) != 2:
        return False
    stage_id, output_name = parts
    return output_name in available_outputs.get(stage_id, set())


def _validate_bindings(
    bindings: Any,
    stage_path: str,
    prompt_text: str | None,
    input_names: set[str],
    available_outputs: dict[str, set[str]],
    execution: str,
    context_name: str | None,
    issues: list[ValidationIssue],
) -> None:
    if bindings is None:
        return
    if not _is_list(bindings):
        _add(issues, f"{stage_path}.bindings", "must be a list")
        return
    for index, binding in enumerate(bindings):
        path = f"{stage_path}.bindings[{index}]"
        if not _is_mapping(binding):
            _add(issues, path, "must be a mapping")
            continue
        placeholder = binding.get("placeholder")
        if not isinstance(placeholder, str) or not placeholder:
            _add(issues, f"{path}.placeholder", "must be a non-empty string")
        elif prompt_text is not None and placeholder not in prompt_text:
            _add(issues, f"{path}.placeholder", f"placeholder {placeholder!r} was not found in the prompt text")

        source = binding.get("source")
        if not isinstance(source, str) or not source:
            _add(issues, f"{path}.source", "must be a non-empty string")
        elif not _source_exists(source, input_names, available_outputs, execution, context_name):
            _add(issues, f"{path}.source", f"unknown or unavailable source: {source}")

        fmt = binding.get("format")
        if fmt is not None and fmt not in VALID_BINDING_FORMATS:
            _add(issues, f"{path}.format", f"must be one of {sorted(VALID_BINDING_FORMATS)}")


def _validate_map(stage: dict[str, Any], stage_path: str, input_names: set[str], available_outputs: dict[str, set[str]], issues: list[ValidationIssue]) -> str | None:
    execution = stage.get("execution")
    map_spec = stage.get("map")
    if execution == "single":
        if map_spec is not None:
            _add(issues, f"{stage_path}.map", "is not allowed when execution=single")
        return None

    if not _is_mapping(map_spec):
        _add(issues, f"{stage_path}.map", f"is required when execution={execution}")
        return None

    over = map_spec.get("over")
    if not isinstance(over, str) or not over:
        _add(issues, f"{stage_path}.map.over", "must be a non-empty source reference")
    elif not _source_exists(over, input_names, available_outputs, str(execution), None):
        _add(issues, f"{stage_path}.map.over", f"unknown or unavailable source: {over}")

    item_name = map_spec.get("item_name")
    if item_name is not None:
        _validate_id(item_name, f"{stage_path}.map.item_name", issues)
    else:
        _add(issues, f"{stage_path}.map.item_name", "is required")

    context_name = map_spec.get("context_name")
    if execution == "map_with_context":
        if context_name is None:
            _add(issues, f"{stage_path}.map.context_name", "is required when execution=map_with_context")
        else:
            _validate_id(context_name, f"{stage_path}.map.context_name", issues)
    elif context_name is not None:
        _add(issues, f"{stage_path}.map.context_name", "is only allowed when execution=map_with_context")

    strategy = map_spec.get("context_strategy")
    if strategy is not None and strategy not in {"concat"}:
        _add(issues, f"{stage_path}.map.context_strategy", "must be 'concat' in v1")

    return str(context_name) if isinstance(context_name, str) else None


def _validate_response(response: Any, stage_path: str, execution: str, root: Path, issues: list[ValidationIssue]) -> None:
    path = f"{stage_path}.response"
    if not _is_mapping(response):
        _add(issues, path, "must be a mapping")
        return
    kind = response.get("kind")
    if kind not in VALID_RESPONSE_KINDS:
        _add(issues, f"{path}.kind", f"must be one of {sorted(VALID_RESPONSE_KINDS)}")

    if execution == "single":
        if not isinstance(response.get("file"), str) or not response.get("file"):
            _add(issues, f"{path}.file", "is required when execution=single")
        for field in ("per_item_file", "aggregate_file", "aggregate_strategy"):
            if field in response:
                _add(issues, f"{path}.{field}", "is only allowed for map executions")
    else:
        if "file" in response:
            _add(issues, f"{path}.file", "is only allowed when execution=single")
        if "aggregate_strategy" in response and response["aggregate_strategy"] not in VALID_AGGREGATE_STRATEGIES:
            _add(issues, f"{path}.aggregate_strategy", f"must be one of {sorted(VALID_AGGREGATE_STRATEGIES)}")

    schema = response.get("schema")
    if schema is not None:
        if kind != "json":
            _add(issues, f"{path}.schema", "is only allowed when response.kind=json")
        elif not isinstance(schema, str) or not schema.strip():
            _add(issues, f"{path}.schema", "must be a non-empty string")
        elif not (root / schema).is_file():
            _add(issues, f"{path}.schema", f"file does not exist relative to root: {schema}")


def _validate_outputs(outputs: Any, stage_path: str, execution: str, issues: list[ValidationIssue]) -> set[str]:
    names: set[str] = set()
    if not _is_mapping(outputs) or not outputs:
        _add(issues, f"{stage_path}.outputs", "must be a non-empty mapping")
        return names
    for name, spec in outputs.items():
        output_path = f"{stage_path}.outputs.{name}"
        _validate_id(name, output_path, issues)
        names.add(str(name))
        if not _is_mapping(spec):
            _add(issues, output_path, "must be a mapping")
            continue
        source = spec.get("source")
        if not isinstance(source, str) or not source:
            _add(issues, f"{output_path}.source", "must be a non-empty response reference")
            continue
        if execution == "single":
            if source != "response" and not source.startswith("response."):
                _add(issues, f"{output_path}.source", "must be 'response' or 'response.<field>'")
        else:
            if source not in {"response.items", "response.aggregate"}:
                _add(issues, f"{output_path}.source", "map outputs must be 'response.items' or 'response.aggregate'")
    return names


def validate_pipeline_data(data: Any, root: Path) -> None:
    issues: list[ValidationIssue] = []
    if not _is_mapping(data):
        raise PipelineValidationError([ValidationIssue("$", "pipeline YAML must be a mapping")])

    if data.get("version") != 1:
        _add(issues, "version", "must be 1")
    _validate_id(data.get("id"), "id", issues)
    _validate_defaults(data.get("defaults"), issues)

    input_names = _validate_inputs(data.get("inputs"), issues)
    stages = data.get("stages")
    if not _is_list(stages) or not stages:
        _add(issues, "stages", "must be a non-empty list")
        raise PipelineValidationError(issues)

    seen_stage_ids: set[str] = set()
    available_outputs: dict[str, set[str]] = {}

    for index, stage in enumerate(stages):
        stage_path = f"stages[{index}]"
        if not _is_mapping(stage):
            _add(issues, stage_path, "must be a mapping")
            continue

        stage_id = stage.get("id")
        _validate_id(stage_id, f"{stage_path}.id", issues)
        if isinstance(stage_id, str):
            if stage_id in seen_stage_ids:
                _add(issues, f"{stage_path}.id", f"duplicate stage id: {stage_id}")
            seen_stage_ids.add(stage_id)

        stage_type = stage.get("type")
        if stage_type not in VALID_STAGE_TYPES:
            _add(issues, f"{stage_path}.type", f"must be one of {sorted(VALID_STAGE_TYPES)}")

        execution = stage.get("execution")
        if execution not in VALID_EXECUTIONS:
            _add(issues, f"{stage_path}.execution", f"must be one of {sorted(VALID_EXECUTIONS)}")
            execution = "single"

        context_name = _validate_map(stage, stage_path, input_names, available_outputs, issues)
        prompt_text = _validate_prompt(stage.get("prompt"), stage_path, root, issues)
        _validate_bindings(
            stage.get("bindings"),
            stage_path,
            prompt_text,
            input_names,
            available_outputs,
            str(execution),
            context_name,
            issues,
        )
        _validate_response(stage.get("response"), stage_path, str(execution), root, issues)
        output_names = _validate_outputs(stage.get("outputs"), stage_path, str(execution), issues)

        _validate_failure(stage.get("failure"), f"{stage_path}.failure", issues)
        model = stage.get("model")
        if model is not None and not _is_mapping(model):
            _add(issues, f"{stage_path}.model", "must be a mapping")

        if isinstance(stage_id, str):
            available_outputs[stage_id] = output_names

    if issues:
        raise PipelineValidationError(issues)


def load_yaml_file(path: Path) -> Any:
    if yaml is None:
        raise RuntimeError("PyYAML is not installed. Install requirements.txt or run: pip install PyYAML")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def validate_pipeline_file(path: Path, root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parent.parent
    validate_pipeline_data(load_yaml_file(path), root.resolve())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Prompt Pipeline YAML v1 file")
    parser.add_argument("pipeline", help="Path to a pipeline YAML file")
    parser.add_argument(
        "--root",
        help="Lab backend root for resolving prompt/schema files. Defaults to prompts_lab/lab_backend.",
    )
    args = parser.parse_args(argv)

    pipeline_path = Path(args.pipeline)
    root = Path(args.root) if args.root else Path(__file__).resolve().parent.parent
    try:
        validate_pipeline_file(pipeline_path, root)
    except PipelineValidationError as exc:
        print(f"Invalid pipeline: {pipeline_path}", file=sys.stderr)
        for issue in exc.issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI should provide concise failure
        print(f"Could not validate {pipeline_path}: {exc}", file=sys.stderr)
        return 2

    print(f"Valid pipeline: {pipeline_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

