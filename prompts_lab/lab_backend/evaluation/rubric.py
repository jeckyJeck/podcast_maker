"""Loads judge rubrics from YAML config under common_resources/eval_rubrics/.

A rubric declares scoring dimensions as free text (name + description) so the
dimensions themselves are configurable without touching evaluator code - see
common_resources/eval_rubrics/podcast_quality.yaml for the current default.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from utils.paths import BACKEND_ROOT

RUBRICS_DIR = BACKEND_ROOT.parent / "common_resources" / "eval_rubrics"


class RubricError(Exception):
    pass


@dataclass
class RubricDimension:
    name: str
    description: str


@dataclass
class Rubric:
    id: str
    name: str
    instructions: str
    dimensions: list[RubricDimension]


def load_rubric(rubric_id: str, rubrics_dir: Path | None = None) -> Rubric:
    if "/" in rubric_id or "\\" in rubric_id or rubric_id.startswith("."):
        raise RubricError(f"Invalid rubric id: {rubric_id}")

    root = rubrics_dir or RUBRICS_DIR
    path = root / f"{rubric_id}.yaml"
    if not path.exists():
        raise RubricError(f"Rubric not found: {rubric_id}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    dimensions_raw = data.get("dimensions") or []
    if not dimensions_raw:
        raise RubricError(f"Rubric '{rubric_id}' declares no dimensions")

    dimensions = [
        RubricDimension(name=str(d["name"]), description=str(d.get("description", "")).strip())
        for d in dimensions_raw
    ]

    return Rubric(
        id=data.get("id", rubric_id),
        name=data.get("name", rubric_id),
        instructions=str(data.get("instructions", "")).strip(),
        dimensions=dimensions,
    )


def list_rubrics(rubrics_dir: Path | None = None) -> list[str]:
    root = rubrics_dir or RUBRICS_DIR
    if not root.exists():
        return []
    return sorted(p.stem for p in root.glob("*.yaml"))
