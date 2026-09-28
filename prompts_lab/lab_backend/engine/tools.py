"""Maps contract `tools` entries (see PIPELINE_CONTRACT.md "Tools") to provider-specific
tool objects. Kept in lockstep with VALID_TOOLS in engine/validate_pipeline.py — closed
today, expected to grow.
"""

from __future__ import annotations

from typing import Any, Callable

from google.genai import types

TOOL_FACTORIES: dict[str, Callable[[], Any]] = {
    "google_search": lambda: types.Tool(google_search=types.GoogleSearch()),
}


def resolve_tools(names: list[str] | None) -> list[Any] | None:
    if not names:
        return None
    return [TOOL_FACTORIES[name]() for name in names]
