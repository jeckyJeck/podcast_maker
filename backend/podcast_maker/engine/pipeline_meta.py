"""Facts derived from a pipeline YAML, which is the single source of truth for stage ids,
inputs and output files. Nothing here knows any particular stage or input name.
"""

from __future__ import annotations

from typing import Any


def stage_output_file(stage: dict[str, Any]) -> str | None:
    """The run-relative file holding a stage's final output (aggregate file for map stages)."""
    response = stage.get("response") or {}
    if stage.get("execution") == "single":
        return response.get("file")
    return response.get("aggregate_file")


def stage_output_files(pipeline_data: dict[str, Any]) -> dict[str, str]:
    """{stage_id: output file} in stage order, for stages that persist an output file."""
    files: dict[str, str] = {}
    for stage in pipeline_data.get("stages") or []:
        file_name = stage_output_file(stage)
        if stage.get("id") and file_name:
            files[stage["id"]] = file_name
    return files


def final_stage_id(pipeline_data: dict[str, Any]) -> str | None:
    files = stage_output_files(pipeline_data)
    return list(files)[-1] if files else None


def evaluation_targets(pipeline_data: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    """(content_files, context_files) to judge, each {name: run-relative file}.

    From the optional top-level `evaluation: {content: <stage id | [ids]>, context: [ids]}`
    block; without it, the final stage's output is the content and there is no context.
    """
    files = stage_output_files(pipeline_data)
    spec = pipeline_data.get("evaluation") or {}
    content_ids = spec.get("content")
    if content_ids is None:
        final = final_stage_id(pipeline_data)
        content_ids = [final] if final else []
    elif isinstance(content_ids, str):
        content_ids = [content_ids]
    context_ids = spec.get("context") or []
    return (
        {stage_id: files[stage_id] for stage_id in content_ids if stage_id in files},
        {stage_id: files[stage_id] for stage_id in context_ids if stage_id in files},
    )


def run_label(pipeline_data: dict[str, Any], inputs: dict[str, Any]) -> str | None:
    """Short human label for a run: the value of the first required text input, else the
    first text input, as declared in the YAML."""
    specs = pipeline_data.get("inputs") or {}
    text_inputs = [name for name, spec in specs.items() if (spec or {}).get("type", "text") == "text"]
    required_first = [n for n in text_inputs if specs[n].get("required")] + [
        n for n in text_inputs if not specs[n].get("required")
    ]
    for name in required_first:
        value = inputs.get(name)
        if value:
            return str(value)
    return None
