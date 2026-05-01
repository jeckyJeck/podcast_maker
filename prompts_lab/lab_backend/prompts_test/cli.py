from __future__ import annotations

import argparse
from pathlib import Path

from prompts_test.compare import compare_files, list_run_directories, resolve_run_dir
from prompts_test.io_contracts import ContractError
from prompts_test.stage_runner import RunnerInputs, PromptTestRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompts_test",
        description="Run partial podcast-agent stages with injected artifacts.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Run one stage or a stage chain")
    run_cmd.add_argument("--topic", required=True, help="Podcast topic used by prompts")
    run_cmd.add_argument(
        "--stages",
        default="architect,researcher,outliner,scriptwriter",
        help="Comma-separated stage list",
    )
    run_cmd.add_argument(
        "--host-ids",
        default="sarah_curious,mike_expert",
        help="Comma-separated host IDs",
    )
    run_cmd.add_argument("--format", dest="podcast_format", choices=["dialogue", "solo"], default=None)
    run_cmd.add_argument("--blueprint-file", type=Path)
    run_cmd.add_argument("--research-file", type=Path)
    run_cmd.add_argument("--outline-file", type=Path)
    run_cmd.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parent / "runs")
    run_cmd.add_argument("--run-name", default=None)
    run_cmd.add_argument("--override-architect", type=Path, default=None)
    run_cmd.add_argument("--override-researcher", type=Path, default=None)
    run_cmd.add_argument("--override-outliner", type=Path, default=None)
    run_cmd.add_argument("--override-scriptwriter", type=Path, default=None)

    compare_cmd = sub.add_parser("compare", help="Diff one output file between two runs")
    compare_cmd.add_argument("--run-a", required=True, help="Run name or absolute path")
    compare_cmd.add_argument("--run-b", required=True, help="Run name or absolute path")
    compare_cmd.add_argument(
        "--file",
        default="research.md",
        choices=[
            "blueprint.json",
            "research.md",
            "outline.json",
            "script.txt",
            "prompt_architect.txt",
            "prompt_researcher.txt",
            "prompt_outliner.txt",
            "prompt_scriptwriter.txt",
        ],
    )
    compare_cmd.add_argument("--max-lines", type=int, default=200)
    compare_cmd.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parent / "runs")

    list_cmd = sub.add_parser("list-runs", help="List available run directories")
    list_cmd.add_argument("--runs-root", type=Path, default=Path(__file__).resolve().parent / "runs")

    return parser


def command_run(args: argparse.Namespace) -> int:
    host_ids = [item.strip() for item in args.host_ids.split(",") if item.strip()]
    inputs = RunnerInputs(
        topic=args.topic,
        stages_arg=args.stages,
        host_ids=host_ids,
        podcast_format=args.podcast_format,
        blueprint_file=args.blueprint_file,
        research_file=args.research_file,
        outline_file=args.outline_file,
        runs_root=args.runs_root,
        run_name=args.run_name,
        prompt_override_architect=args.override_architect,
        prompt_override_researcher=args.override_researcher,
        prompt_override_outliner=args.override_outliner,
        prompt_override_scriptwriter=args.override_scriptwriter,
    )

    runner = PromptTestRunner(inputs)
    run_dir = runner.run()

    print(f"Run completed: {run_dir}")
    print(f"Manifest: {run_dir / 'run_manifest.json'}")
    return 0


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
        if args.command == "run":
            return command_run(args)
        if args.command == "compare":
            return command_compare(args)
        if args.command == "list-runs":
            return command_list_runs(args)

        parser.print_help()
        return 1
    except ContractError as error:
        print(f"Contract error: {error}")
        return 2
    except FileNotFoundError as error:
        print(f"File error: {error}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
