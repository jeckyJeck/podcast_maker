from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

from podcast_maker.core.paths import BACKEND_ROOT

StageName = Literal["architect", "researcher", "outliner", "scriptwriter"]
TEMPLATES_ROOT = BACKEND_ROOT / "prompts_test" / "prompt_templates"


class PromptTemplateRecord(TypedDict):
    id: str
    user_id: str
    stage: StageName
    name: str
    prompt_text: str
    created_at_utc: str
    updated_at_utc: str


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_user_dir(user_id: str) -> Path:
    safe_user = user_id.replace("/", "_").replace("\\", "_").replace(":", "_").strip() or "unknown"
    user_dir = TEMPLATES_ROOT / safe_user
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _template_path(user_id: str, template_id: str) -> Path:
    return _safe_user_dir(user_id) / f"{template_id}.json"


def is_valid_template_id(template_id: str) -> bool:
    if not template_id or template_id.startswith("."):
        return False
    if "/" in template_id or "\\" in template_id:
        return False
    return True


def list_templates(user_id: str, stage: StageName | None = None) -> list[PromptTemplateRecord]:
    rows: list[PromptTemplateRecord] = []
    user_dir = _safe_user_dir(user_id)
    for path in user_dir.glob("*.json"):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(row, dict):
            continue
        if stage and row.get("stage") != stage:
            continue
        rows.append(row)  # type: ignore[arg-type]

    rows.sort(key=lambda item: str(item.get("updated_at_utc", "")), reverse=True)
    return rows


def get_template(user_id: str, template_id: str) -> PromptTemplateRecord:
    path = _template_path(user_id, template_id)
    row = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(row, dict):
        raise ValueError("Template content is invalid")
    return row  # type: ignore[return-value]


def create_template(
    user_id: str,
    template_id: str,
    stage: StageName,
    name: str,
    prompt_text: str,
) -> PromptTemplateRecord:
    stamp = now_utc_iso()
    row: PromptTemplateRecord = {
        "id": template_id,
        "user_id": user_id,
        "stage": stage,
        "name": name,
        "prompt_text": prompt_text,
        "created_at_utc": stamp,
        "updated_at_utc": stamp,
    }
    path = _template_path(user_id, template_id)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def update_template(
    user_id: str,
    template_id: str,
    name: str | None = None,
    prompt_text: str | None = None,
) -> PromptTemplateRecord:
    row = get_template(user_id, template_id)
    if name is not None:
        row["name"] = name
    if prompt_text is not None:
        row["prompt_text"] = prompt_text
    row["updated_at_utc"] = now_utc_iso()

    path = _template_path(user_id, template_id)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
    return row


def delete_template(user_id: str, template_id: str) -> None:
    path = _template_path(user_id, template_id)
    path.unlink()
