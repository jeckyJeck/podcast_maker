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


def default_evaluation_files(pipeline_data: dict[str, Any]) -> dict[str, str]:
    """Default content to judge for a run: the final stage's output file, {stage_id: file}.
    Evaluation is a separate process and keeps its own settings; the pipeline YAML only says what files exist."""
    final = final_stage_id(pipeline_data)
    return {final: stage_output_files(pipeline_data)[final]} if final else {}


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
