"""Resolves a pipeline's declared `inputs` block against a raw payload, per
PIPELINE_CONTRACT.md "Inputs": applies defaults, enforces required, coerces by type.
"""

from __future__ import annotations

from typing import Any


class InputResolutionError(ValueError):
    pass


def _coerce(name: str, value: Any, input_type: str) -> Any:
    if input_type == "text":
        return str(value)
    if input_type == "number":
        if isinstance(value, bool):
            raise InputResolutionError(f"input {name!r} must be a number")
        try:
            return float(value) if not isinstance(value, (int, float)) else value
        except (TypeError, ValueError) as exc:
            raise InputResolutionError(f"input {name!r} must be a number") from exc
    if input_type == "boolean":
        if isinstance(value, bool):
            return value
        raise InputResolutionError(f"input {name!r} must be a boolean")
    if input_type == "json":
        return value
    raise InputResolutionError(f"input {name!r} has unknown type {input_type!r}")


def resolve_inputs(input_specs: dict[str, dict[str, Any]], raw: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for name, spec in (input_specs or {}).items():
        input_type = spec.get("type", "text")
        if name in raw and raw[name] is not None:
            resolved[name] = _coerce(name, raw[name], input_type)
        elif "default" in spec:
            resolved[name] = spec["default"]
        elif spec.get("required"):
            raise InputResolutionError(f"missing required input: {name}")
        else:
            resolved[name] = None
    return resolved
