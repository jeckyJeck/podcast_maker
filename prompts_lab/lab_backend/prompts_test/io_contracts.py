from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STAGE_ORDER = ["architect", "researcher", "outliner", "scriptwriter"]


class ContractError(ValueError):
    """Raised when stage input/output contract is violated."""


@dataclass
class LoadedInputs:
    topic: str
    blueprint: dict[str, Any] | None = None
    research: str | None = None
    outline: dict[str, Any] | None = None


def parse_stages(stages_arg: str | None) -> list[str]:
    if not stages_arg:
        return STAGE_ORDER.copy()

    stages = [item.strip().lower() for item in stages_arg.split(",") if item.strip()]
    if not stages:
        raise ContractError("No stages provided.")

    invalid = [stage for stage in stages if stage not in STAGE_ORDER]
    if invalid:
        raise ContractError(f"Invalid stage(s): {', '.join(invalid)}")

    return stages


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ContractError(f"JSON file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_text_file(path: Path) -> str:
    if not path.exists():
        raise ContractError(f"Text file not found: {path}")
    return path.read_text(encoding="utf-8")


def validate_prerequisites(
    stage: str,
    topic: str,
    blueprint: dict[str, Any] | None,
    research: str | None,
    outline: dict[str, Any] | None,
) -> None:
    if not topic.strip():
        raise ContractError("topic is required.")

    if stage == "researcher" and blueprint is None:
        raise ContractError("researcher requires blueprint (inject blueprint or run architect first).")

    if stage == "outliner":
        if blueprint is None:
            raise ContractError("outliner requires blueprint (inject blueprint or run architect first).")
        if research is None:
            raise ContractError("outliner requires research (inject research or run researcher first).")

    if stage == "scriptwriter":
        if outline is None:
            raise ContractError("scriptwriter requires outline (inject outline or run outliner first).")
        if research is None:
            raise ContractError("scriptwriter requires research (inject research or run researcher first).")
