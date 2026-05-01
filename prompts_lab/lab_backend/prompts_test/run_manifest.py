from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class StageRecord:
    stage: str
    started_at_utc: str
    finished_at_utc: str
    duration_seconds: float
    output_files: list[str] = field(default_factory=list)


@dataclass
class RunManifest:
    run_id: str
    topic: str
    stages: list[str]
    model: str
    format: str
    host_ids: list[str]
    created_at_utc: str
    run_directory: str
    injected_inputs: dict[str, str]
    prompt_overrides: dict[str, str]
    stage_records: list[StageRecord]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["stage_records"] = [asdict(record) for record in self.stage_records]
        return payload

    def write(self, destination: Path) -> None:
        destination.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )



def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
