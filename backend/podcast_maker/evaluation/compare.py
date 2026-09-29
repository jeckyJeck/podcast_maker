from __future__ import annotations

from pathlib import Path
import difflib


def resolve_run_dir(runs_root: Path, run_ref: str) -> Path:
    candidate = Path(run_ref)
    if candidate.exists():
        return candidate

    candidate = runs_root / run_ref
    if candidate.exists():
        return candidate

    raise FileNotFoundError(f"Run directory not found: {run_ref}")


def compare_files(run_a: Path, run_b: Path, file_name: str, max_lines: int = 200) -> str:
    file_a = run_a / file_name
    file_b = run_b / file_name

    if not file_a.exists():
        raise FileNotFoundError(f"Missing in run A: {file_a}")
    if not file_b.exists():
        raise FileNotFoundError(f"Missing in run B: {file_b}")

    text_a = file_a.read_text(encoding="utf-8", errors="replace").splitlines()
    text_b = file_b.read_text(encoding="utf-8", errors="replace").splitlines()

    diff = list(
        difflib.unified_diff(
            text_a,
            text_b,
            fromfile=str(file_a),
            tofile=str(file_b),
            lineterm="",
        )
    )

    if not diff:
        return "No differences found."

    if max_lines > 0:
        diff = diff[:max_lines]

    return "\n".join(diff)


def list_run_directories(runs_root: Path) -> list[Path]:
    if not runs_root.exists():
        return []
    return sorted([path for path in runs_root.iterdir() if path.is_dir()], reverse=True)
