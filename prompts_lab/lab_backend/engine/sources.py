"""Source-reference resolution and binding rendering for the generic pipeline executor.

Implements the "Source References" and "Bindings" sections of PIPELINE_CONTRACT.md:
inputs.<name>, <stage>.<output>, item[.field], context.<name>.
"""

from __future__ import annotations

import json
from typing import Any


class SourceResolutionError(ValueError):
    pass


def _get_path(data: Any, parts: list[str]) -> Any:
    current = data
    for part in parts:
        if isinstance(current, dict):
            if part not in current:
                raise SourceResolutionError(f"missing field {part!r}")
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            current = current[int(part)]
        else:
            raise SourceResolutionError(f"cannot resolve {part!r} on {type(current).__name__}")
    return current


def resolve_source(source: str, context: dict[str, Any]) -> Any:
    """Resolve a contract source reference against the run context.

    context is expected to hold:
      - "inputs": dict of resolved pipeline inputs
      - "<stage_id>": dict of that stage's outputs (once it has run)
      - "item": current map item (map/map_with_context stages only)
      - "context": dict of named accumulated context (map_with_context only)
    """
    if source == "item":
        if "item" not in context:
            raise SourceResolutionError("'item' is only available in map stages")
        return context["item"]

    if source.startswith("item."):
        if "item" not in context:
            raise SourceResolutionError("'item.*' is only available in map stages")
        return _get_path(context["item"], source.split(".")[1:])

    if source.startswith("inputs."):
        name = source.split(".", 1)[1]
        if name not in context.get("inputs", {}):
            raise SourceResolutionError(f"unknown input: {name}")
        return context["inputs"][name]

    if source.startswith("context."):
        name = source.split(".", 1)[1]
        ctx = context.get("context", {})
        if name not in ctx:
            raise SourceResolutionError(f"unknown context value: {name}")
        return ctx[name]

    parts = source.split(".")
    if len(parts) != 2:
        raise SourceResolutionError(f"unresolvable source reference: {source}")
    stage_id, output_name = parts
    stage_outputs = context.get(stage_id)
    if stage_outputs is None or output_name not in stage_outputs:
        raise SourceResolutionError(f"unknown or unavailable source: {source}")
    return stage_outputs[output_name]


def format_value(value: Any, fmt: str | None) -> str:
    if fmt == "text":
        return "" if value is None else str(value)
    if fmt == "json":
        return json.dumps(value, ensure_ascii=False, indent=2)
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def render_bindings(prompt_text: str, bindings: list[dict[str, Any]], context: dict[str, Any]) -> str:
    rendered = prompt_text
    for binding in bindings or []:
        placeholder = binding["placeholder"]
        value = resolve_source(binding["source"], context)
        rendered = rendered.replace(placeholder, format_value(value, binding.get("format")))
    return rendered


def safe_filename(name: str) -> str:
    import re

    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name).strip())
    return sanitized.strip("_") or "item"


def render_file_pattern(pattern: str, context: dict[str, Any]) -> str:
    """Render a run-relative file path pattern, e.g. 'outputs/research_{{ item.segment_name }}.md'.

    Only the substituted placeholder values are filename-sanitized; literal path
    separators and extensions in the pattern are preserved as written.
    """
    import re

    ref_re = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")

    def replace(match: "re.Match[str]") -> str:
        return safe_filename(str(resolve_source(match.group(1), context)))

    return ref_re.sub(replace, pattern)
