from __future__ import annotations

import argparse
from pathlib import Path

from prompts_test.compare import compare_files, list_run_directories, resolve_run_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompts_test",
        description="Inspect and compare pipeline run directories. Use the lab_backend "
        "API's POST /pipelines/run to execute a pipeline (see PIPELINE_CONTRACT.md).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    compare_cmd = sub.add_parser("compare", help="Diff one output file between two runs")
    compare_cmd.add_argument("--run-a", required=True, help="Run name or absolute path")
    compare_cmd.add_argument("--run-b", required=True, help="Run name or absolute path")
    compare_cmd.add_argument(
        "--file",
        required=True,
        help="Run-relative file path to diff, e.g. outputs/blueprint.json (pipeline-defined; see run_manifest.json)",
    )
    compare_cmd.add_argument("--max-lines", type=int, default=200)
    compare_cmd.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parent / "runs")

    list_cmd = sub.add_parser("list-runs", help="List available run directories")
    list_cmd.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parent / "runs")

    return parser


def command_compare(args: argparse.Namespace) -> int:
    run_a = resolve_run_dir(args.runs_root, args.run_a)
    run_b = resolve_run_dir(args.runs_root, args.run_b)
    diff = compare_files(run_a, run_b, args.file, max_lines=args.max_lines)
    print(diff)
    return 0


def command_list_runs(args: argparse.Namespace) -> int:
    runs = list_run_directories(args.runs_root)
    if not runs:
        print(f"No runs found in {args.runs_root}")
        return 0

    for run in runs:
        print(run)
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        if args.command == "compare":
            return command_compare(args)
        if args.command == "list-runs":
            return command_list_runs(args)

        parser.print_help()
        return 1
    except FileNotFoundError as error:
        print(f"File error: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
