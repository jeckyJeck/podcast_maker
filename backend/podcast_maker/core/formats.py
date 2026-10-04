"""Production "formats": every pipeline under resources/pipelines is a format, and its YAML `id`
is the format name. Nothing here knows any stage or input name.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from podcast_maker.core.hosts_config import format_hosts_for_prompt, get_host_profile
from podcast_maker.core.paths import BACKEND_ROOT, PIPELINES_DIR
from podcast_maker.engine.inputs import resolve_inputs
from podcast_maker.engine.pipeline_meta import stage_output_files
from podcast_maker.engine.validate_pipeline import validate_pipeline_data

# Keys of the podcast's `urls` record that are not stage artifacts.
PIPELINE_URL_KEY = "pipeline"
TAIL_URL_KEYS = ("audio", "transcript", "transcript_vtt")
RESERVED_URL_KEYS = {PIPELINE_URL_KEY, *TAIL_URL_KEYS}

# Inputs the platform fills in by name for every podcast request.
PLATFORM_INPUTS = {"topic", "host_profiles", "host_name"}

_FORMAT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class FormatError(ValueError):
    pass


def pipeline_path(format_id: str):
    if not _FORMAT_ID_RE.match(format_id or ""):
        raise FormatError(f"Invalid format: {format_id!r}")
    path = PIPELINES_DIR / format_id / "pipeline.yaml"
    if not path.is_file():
        raise FormatError(f"Unknown format: {format_id!r}")
    return path


def load_pipeline_text(format_id: str) -> str:
    return pipeline_path(format_id).read_text(encoding="utf-8")


def parse_and_validate(pipeline_text: str) -> dict[str, Any]:
    data = yaml.safe_load(pipeline_text)
    validate_pipeline_data(data, BACKEND_ROOT)
    clashes = sorted({s["id"] for s in data["stages"]} & RESERVED_URL_KEYS)
    if clashes:
        raise FormatError(f"Stage ids {clashes} clash with reserved artifact names {sorted(RESERVED_URL_KEYS)}")
    return data


def list_formats() -> list[dict[str, Any]]:
    formats = []
    for path in sorted(PIPELINES_DIR.glob("*/pipeline.yaml")):
        try:
            data = parse_and_validate(path.read_text(encoding="utf-8"))
        except Exception:  # an invalid pipeline is simply not offered
            continue
        formats.append(
            {
                "id": data["id"],
                "name": data.get("name", data["id"]),
                "description": data.get("description", ""),
                "host_count": data.get("host_count"),
                "inputs": user_inputs(data),
            }
        )
    return formats


def user_inputs(pipeline_data: dict[str, Any]) -> list[dict[str, Any]]:
    """The declared inputs a request may set (everything but the platform inputs), in YAML order,
    so a client can build a form for them. `json` inputs are included; clients decide what to show."""
    specs = []
    for name, spec in (pipeline_data.get("inputs") or {}).items():
        if name in PLATFORM_INPUTS:
            continue
        spec = spec or {}
        specs.append(
            {
                "name": name,
                "type": spec.get("type", "text"),
                "required": bool(spec.get("required", False)) and "default" not in spec,
                "default": spec.get("default"),
            }
        )
    return specs


def choose_format(host_count: int) -> str:
    """Default format when a request names none: the first one written for this many hosts."""
    for fmt in list_formats():
        if fmt["host_count"] == host_count:
            return fmt["id"]
    raise FormatError(f"No format available for {host_count} host(s)")


def stage_ids(pipeline_data: dict[str, Any]) -> list[str]:
    return [stage["id"] for stage in pipeline_data["stages"]]


def artifact_file_names(pipeline_data: dict[str, Any]) -> dict[str, str]:
    """{stage_id: file name used in the bucket}: the basename of the stage's output file
    (e.g. script.txt); if two stages share a basename, the stage id is prefixed."""
    names: dict[str, str] = {}
    for stage_id, rel_path in stage_output_files(pipeline_data).items():
        base = rel_path.replace("\\", "/").rsplit("/", 1)[-1]
        names[stage_id] = f"{stage_id}_{base}" if base in names.values() else base
    return names


def build_inputs(
    pipeline_data: dict[str, Any], topic: str, host_ids: list[str], extra_inputs: dict[str, Any] | None
) -> dict[str, Any]:
    """Resolve the pipeline's declared inputs from the platform inputs (topic, host_profiles, host_name)
    plus any extra inputs the request supplied. Undeclared extras are rejected."""
    declared = pipeline_data.get("inputs") or {}
    overridden = sorted(set(extra_inputs or {}) & PLATFORM_INPUTS)
    if overridden:
        raise FormatError(f"Inputs {overridden} are supplied by the platform and cannot be set")
    unknown = sorted(set(extra_inputs or {}) - set(declared))
    if unknown:
        raise FormatError(f"Pipeline {pipeline_data['id']!r} declares no input(s): {unknown}")
    raw = {
        "topic": topic,
        "host_profiles": format_hosts_for_prompt(host_ids),
        "host_name": get_host_profile(host_ids[0]).name,
        **(extra_inputs or {}),
    }
    try:
        return resolve_inputs(declared, raw)
    except ValueError as exc:
        raise FormatError(str(exc)) from exc
