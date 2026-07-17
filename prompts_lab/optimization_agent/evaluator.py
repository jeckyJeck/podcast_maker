from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

try:
    from google import genai
except ImportError:  # pragma: no cover - handled at runtime
    genai = None

try:
    from rich.console import Console
except ImportError:  # pragma: no cover - optional dependency
    Console = None


EVALUATOR_MODEL = "gemini-2.5-pro"
ROOT = Path(__file__).resolve().parent
RUNS_DIR = ROOT / "runs"
console = Console() if Console else None


class EvaluationError(Exception):
    pass


def log_print(message: str) -> None:
    if console:
        console.print(message)
    else:
        print(message)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        data = json.loads(stripped[start : end + 1])
    if not isinstance(data, dict):
        raise EvaluationError("Evaluator response was not a JSON object")
    return data


def call_gemini(prompt: str) -> str:
    if genai is None:
        raise EvaluationError("google-genai is not installed. Install requirements.txt first.")
    load_dotenv(ROOT / ".env")
    start = time.perf_counter()
    client = genai.Client()
    response = client.models.generate_content(model=EVALUATOR_MODEL, contents=prompt)
    text = getattr(response, "text", None)
    if not text:
        raise EvaluationError("Gemini evaluator returned an empty response")
    duration_ms = int((time.perf_counter() - start) * 1000)
    return text, duration_ms


def build_prompt(run_dir: Path, manifest: dict[str, Any]) -> str:
    goals = read_text(ROOT / "evaluation" / "goals.md")
    evaluator_prompt = read_text(ROOT / "evaluation" / "evaluator_prompt.md")
    script = read_text(run_dir / "script.txt")
    topic = manifest.get("user_inputs", {}).get("topic", "")
    fmt = manifest.get("user_inputs", {}).get("format", "")
    return "\n\n".join(
        [
            evaluator_prompt,
            "## Episode Metadata",
            f"Topic: {topic}",
            f"Format: {fmt}",
            "## Goals Document",
            goals,
            "## Script",
            script,
        ]
    )


def normalize_evaluation(data: dict[str, Any], run_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    if "overall_score" not in data:
        raise EvaluationError("Evaluation JSON missing overall_score")
    if "dimension_scores" not in data or not isinstance(data["dimension_scores"], dict):
        raise EvaluationError("Evaluation JSON missing dimension_scores object")
    user_inputs = manifest.get("user_inputs", {})
    return {
        "run_id": run_id,
        "topic": user_inputs.get("topic"),
        "format": user_inputs.get("format"),
        "evaluator_model": EVALUATOR_MODEL,
        "overall_score": float(data["overall_score"]),
        "dimension_scores": {str(k): float(v) for k, v in data["dimension_scores"].items()},
        "reasoning": str(data.get("reasoning", "")),
        "evaluated_at": utc_now(),
    }


def evaluate_run(run_id: str) -> dict[str, Any]:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise EvaluationError(f"Run not found: {run_id}")
    manifest = json.loads(read_text(run_dir / "manifest.json"))
    if manifest.get("overall_status") != "ok":
        raise EvaluationError(f"Cannot evaluate failed run: {run_id}")
    if not (run_dir / "script.txt").exists():
        raise EvaluationError(f"Run has no script.txt: {run_id}")

    raw, duration_ms = call_gemini(build_prompt(run_dir, manifest))
    normalized = normalize_evaluation(extract_json(raw), run_id, manifest)
    normalized["duration_ms"] = duration_ms
    write_text(run_dir / "evaluation.json", json.dumps(normalized, ensure_ascii=False, indent=2))
    return normalized


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a completed podcast run")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        result = evaluate_run(args.run_id)
        log_print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        log_print(f"Evaluation failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

