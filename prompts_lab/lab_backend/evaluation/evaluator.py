"""LLM-as-a-judge evaluation.

`evaluate()` is the generic core: it takes arbitrary named content (usually the
final output of a pipeline run) plus a Rubric and returns structured scores. It
has no opinion about filenames, run directories, or pipeline shape - callers
decide what to hand it. `evaluate_run()` is a thin wiring helper that reads a
file out of a run directory, evaluates it, and persists the result there.

Not wired to any trigger (API route, pipeline hook, etc.) here by design - see
app/routers/prompts_test_api.py for the on-demand HTTP entry point.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluation.rubric import Rubric, load_rubric
from services.llm_provider import LLMProvider, LLMResponseParseError
from services.llm_provider_factory import build_llm_provider


class EvaluationError(Exception):
    pass


@dataclass
class DimensionScore:
    name: str
    score: float
    rationale: str = ""


@dataclass
class EvaluationResult:
    rubric_id: str
    overall_score: float
    dimensions: list[DimensionScore]
    reasoning: str = ""
    suggestions: list[str] = field(default_factory=list)
    evaluator_model: str = ""
    evaluated_at_utc: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rubric_id": self.rubric_id,
            "overall_score": self.overall_score,
            "dimensions": [
                {"name": d.name, "score": d.score, "rationale": d.rationale} for d in self.dimensions
            ],
            "reasoning": self.reasoning,
            "suggestions": self.suggestions,
            "evaluator_model": self.evaluator_model,
            "evaluated_at_utc": self.evaluated_at_utc,
            "duration_ms": self.duration_ms,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _build_judge_prompt(rubric: Rubric, content: dict[str, str], context: dict[str, str] | None) -> str:
    dimension_lines = "\n".join(f"- {d.name}: {d.description}" for d in rubric.dimensions)
    dimension_names = ", ".join(f'"{d.name}"' for d in rubric.dimensions)

    sections = [
        "You are an expert judge evaluating generated content against a rubric.",
        rubric.instructions,
        "## Rubric Dimensions",
        dimension_lines,
        "## Content To Evaluate",
    ]
    for name, text in content.items():
        sections.append(f"### {name}\n{text}")

    if context:
        sections.append(
            "## Additional Context\n"
            "The sections below are supporting context, not content to score directly. "
            "If a section looks like a template with {{placeholder}} markers, treat it as the "
            "generator's configuration (filled in programmatically per run), not literal output. "
            "Use context only to explain scores and, if useful, to suggest what could change in "
            "the generation process to improve the scored content."
        )
        for name, text in context.items():
            sections.append(f"### {name}\n{text}")

    sections.append(
        "## Response Format\n"
        "Return ONLY valid JSON, no markdown fences or commentary, with this exact shape:\n"
        "{\n"
        '  "overall_score": 7.2,\n'
        '  "dimensions": [\n'
        f'    {{"name": "{rubric.dimensions[0].name}", "score": 8.0, "rationale": "..."}}\n'
        "    ...\n"
        "  ],\n"
        '  "reasoning": "concise overall explanation",\n'
        '  "suggestions": ["optional, only if context was provided - concrete changes to the '
        'generation process that would likely raise the score"]\n'
        "}\n"
        f"Scores are floats from 0 to 10. Include exactly one entry per rubric dimension, using "
        f"these exact names: {dimension_names}."
    )
    return "\n\n".join(sections)


def _parse_judge_response(data: dict[str, Any], rubric: Rubric) -> tuple[float, list[DimensionScore], str, list[str]]:
    if "overall_score" not in data:
        raise EvaluationError("Judge response missing overall_score")
    dimensions_raw = data.get("dimensions")
    if not isinstance(dimensions_raw, list) or not dimensions_raw:
        raise EvaluationError("Judge response missing dimensions list")

    dimensions = [
        DimensionScore(
            name=str(item.get("name", "")),
            score=float(item.get("score", 0)),
            rationale=str(item.get("rationale", "")),
        )
        for item in dimensions_raw
    ]

    expected_names = {d.name for d in rubric.dimensions}
    returned_names = {d.name for d in dimensions}
    if not expected_names & returned_names:
        raise EvaluationError(
            f"Judge response dimensions {sorted(returned_names)} don't match rubric dimensions {sorted(expected_names)}"
        )

    suggestions = data.get("suggestions") or []
    if not isinstance(suggestions, list):
        suggestions = [str(suggestions)]

    return float(data["overall_score"]), dimensions, str(data.get("reasoning", "")), [str(s) for s in suggestions]


def evaluate(
    content: dict[str, str],
    rubric: Rubric,
    context: dict[str, str] | None = None,
    llm_provider: LLMProvider | None = None,
    temperature: float = 0.0,
) -> EvaluationResult:
    """Judge `content` (named text sections) against `rubric`.

    `context` is optional supporting material (e.g. the pipeline template that
    produced `content`) used only to explain scores / suggest improvements -
    it is never scored directly.
    """
    if not content:
        raise EvaluationError("evaluate() requires at least one content section")

    provider = llm_provider or build_llm_provider("gemini")
    prompt = _build_judge_prompt(rubric, content, context)

    start = time.perf_counter()
    try:
        raw = provider.generate_json(prompt, temperature=temperature, metadata={"stage": f"judge:{rubric.id}"})
    except LLMResponseParseError as exc:
        raise EvaluationError(f"Judge returned unparseable response: {exc}") from exc
    duration_ms = int((time.perf_counter() - start) * 1000)

    overall_score, dimensions, reasoning, suggestions = _parse_judge_response(raw, rubric)

    return EvaluationResult(
        rubric_id=rubric.id,
        overall_score=overall_score,
        dimensions=dimensions,
        reasoning=reasoning,
        suggestions=suggestions,
        evaluator_model=getattr(provider, "model", ""),
        evaluated_at_utc=_utc_now(),
        duration_ms=duration_ms,
    )


def evaluate_run(
    run_dir: Path,
    content_files: dict[str, str],
    rubric_id: str = "podcast_quality",
    context_files: dict[str, str] | None = None,
    llm_provider: LLMProvider | None = None,
) -> EvaluationResult:
    """Read `content_files`/`context_files` (name -> relative path within run_dir),
    evaluate them, and persist the result to `evaluation.json` in run_dir.

    Caller is responsible for validating that paths stay within run_dir.
    """
    if not run_dir.exists():
        raise EvaluationError(f"Run directory not found: {run_dir}")

    def _read_all(files: dict[str, str] | None) -> dict[str, str]:
        result: dict[str, str] = {}
        for name, rel_path in (files or {}).items():
            path = run_dir / rel_path
            if not path.exists():
                raise EvaluationError(f"File not found in run: {rel_path}")
            result[name] = path.read_text(encoding="utf-8", errors="replace")
        return result

    content = _read_all(content_files)
    context = _read_all(context_files) if context_files else None
    rubric = load_rubric(rubric_id)

    result = evaluate(content, rubric, context=context, llm_provider=llm_provider)
    (run_dir / "evaluation.json").write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result
