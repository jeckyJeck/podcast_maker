import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from dotenv import load_dotenv

from podcast_maker.core.architect import Architect
from podcast_maker.core.outliner import Outliner
from podcast_maker.core.paths import BACKEND_ROOT
from podcast_maker.core.prompt_manager import PodcastConfig
from podcast_maker.core.researcher import Researcher
from podcast_maker.core.scriptwriter import ScriptWriter

from prompts_test.io_contracts import (
    ContractError,
    parse_stages,
    load_json_file,
    load_text_file,
    validate_prerequisites,
)
from podcast_maker.services.llm_provider_factory import build_llm_provider
from prompts_test.prompt_resolver import InstrumentedOverridePromptManager
from prompts_test.run_manifest import RunManifest, StageRecord, utc_now_iso

MODEL_NAME = "gemini-2.5-flash"
DEFAULT_HOST_IDS = ["sarah_curious", "mike_expert"]


@dataclass
class RunnerInputs:
    topic: str
    stages_arg: str | None = None
    host_ids: list[str] | None = None
    podcast_format: str | None = None
    blueprint_file: Path | None = None
    research_file: Path | None = None
    outline_file: Path | None = None
    runs_root: Path | None = None
    run_name: str | None = None
    prompt_override_architect: Path | None = None
    prompt_override_researcher: Path | None = None
    prompt_override_outliner: Path | None = None
    prompt_override_scriptwriter: Path | None = None


class PromptTestRunner:
    def __init__(self, inputs: RunnerInputs):
        self.inputs = inputs
        self.stages = parse_stages(inputs.stages_arg)
        self.host_ids = inputs.host_ids or DEFAULT_HOST_IDS
        self.runs_root = inputs.runs_root or (Path(__file__).resolve().parent / "runs")

        load_dotenv(dotenv_path=BACKEND_ROOT / ".env")

        config = PodcastConfig(
            topic=inputs.topic,
            host_ids=self.host_ids,
            format=inputs.podcast_format,
        )

        self.prompt_overrides = self._build_prompt_overrides()
        self.prompt_manager = InstrumentedOverridePromptManager(config, overrides=self.prompt_overrides)

        llm_provider = build_llm_provider()

        self.architect = Architect(llm_provider, self.prompt_manager)
        self.researcher = Researcher(llm_provider, self.prompt_manager)
        self.outliner = Outliner(llm_provider, self.prompt_manager)
        self.scriptwriter = ScriptWriter(llm_provider, self.prompt_manager)

    def run(self) -> Path:
        self.runs_root.mkdir(parents=True, exist_ok=True)
        run_id = self.inputs.run_name.strip() if self.inputs.run_name else self._default_run_id()
        run_dir = self._make_unique_run_dir(self.runs_root / run_id)
        run_dir.mkdir(parents=True, exist_ok=False)

        injected = self._load_injected_inputs()
        blueprint = cast(dict[str, Any] | None, injected.get("blueprint"))
        research = cast(str | None, injected.get("research"))
        outline = cast(dict[str, Any] | None, injected.get("outline"))
        script = None

        stage_records: list[StageRecord] = []

        for stage in self.stages:
            validate_prerequisites(stage, self.inputs.topic, blueprint, research, outline)
            started_iso = utc_now_iso()
            started = time.perf_counter()
            output_files: list[str] = []

            if stage == "architect":
                blueprint = self.architect.generate_blueprint(self.inputs.topic)
                output_files.append(self._write_json(run_dir / "blueprint.json", blueprint))

            elif stage == "researcher":
                if blueprint is None:
                    raise ContractError("researcher requires blueprint.")
                blueprint_input = cast(dict, blueprint)
                research = self.researcher.conduct_research(blueprint_input)
                output_files.append(self._write_text(run_dir / "research.md", research))

            elif stage == "outliner":
                if blueprint is None or research is None:
                    raise ContractError("outliner requires blueprint and research.")
                blueprint_input = cast(dict, blueprint)
                research_input = cast(str, research)
                outline = self.outliner.create_outline(blueprint_input, research_input, self.inputs.topic)
                output_files.append(self._write_json(run_dir / "outline.json", outline))

            elif stage == "scriptwriter":
                if outline is None or research is None:
                    raise ContractError("scriptwriter requires outline and research.")
                outline_input = cast(dict, outline)
                research_input = cast(str, research)
                script = self.scriptwriter.write_script(outline_input, research_input, self.inputs.topic)
                output_files.append(self._write_text(run_dir / "script.txt", script))

            prompt_snapshot = self.prompt_manager.resolved_prompts.get(stage)
            if prompt_snapshot:
                output_files.append(self._write_text(run_dir / f"prompt_{stage}.txt", prompt_snapshot))

            elapsed = round(time.perf_counter() - started, 3)
            stage_records.append(
                StageRecord(
                    stage=stage,
                    started_at_utc=started_iso,
                    finished_at_utc=utc_now_iso(),
                    duration_seconds=elapsed,
                    output_files=output_files,
                )
            )

        manifest = RunManifest(
            run_id=run_dir.name,
            topic=self.inputs.topic,
            stages=self.stages,
            model=MODEL_NAME,
            format=(self.inputs.podcast_format or "auto"),
            host_ids=self.host_ids,
            created_at_utc=utc_now_iso(),
            run_directory=str(run_dir),
            injected_inputs=self._injected_sources(),
            prompt_overrides={k: str(v) for k, v in self.prompt_overrides.items()},
            stage_records=stage_records,
        )
        manifest.write(run_dir / "run_manifest.json")

        # Preserve final state artifacts if injected but not regenerated in this run.
        if blueprint is not None and not (run_dir / "blueprint.json").exists():
            self._write_json(run_dir / "blueprint.snapshot.json", blueprint)
        if research is not None and not (run_dir / "research.md").exists():
            self._write_text(run_dir / "research.snapshot.md", research)
        if outline is not None and not (run_dir / "outline.json").exists():
            self._write_json(run_dir / "outline.snapshot.json", outline)
        if script is not None and not (run_dir / "script.txt").exists():
            self._write_text(run_dir / "script.snapshot.txt", script)

        return run_dir

    def _build_prompt_overrides(self) -> dict[str, Path]:
        overrides: dict[str, Path] = {}
        pairs = {
            "architect": self.inputs.prompt_override_architect,
            "researcher": self.inputs.prompt_override_researcher,
            "outliner": self.inputs.prompt_override_outliner,
            "scriptwriter": self.inputs.prompt_override_scriptwriter,
        }
        for stage, path in pairs.items():
            if path is None:
                continue
            if not path.exists():
                raise ContractError(f"Prompt override file not found: {path}")
            overrides[stage] = path
        return overrides

    def _load_injected_inputs(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if self.inputs.blueprint_file:
            data["blueprint"] = load_json_file(self.inputs.blueprint_file)
        if self.inputs.research_file:
            data["research"] = load_text_file(self.inputs.research_file)
        if self.inputs.outline_file:
            data["outline"] = load_json_file(self.inputs.outline_file)
        return data

    def _injected_sources(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.inputs.blueprint_file:
            out["blueprint_file"] = str(self.inputs.blueprint_file)
        if self.inputs.research_file:
            out["research_file"] = str(self.inputs.research_file)
        if self.inputs.outline_file:
            out["outline_file"] = str(self.inputs.outline_file)
        return out

    def _default_run_id(self) -> str:
        safe_topic = re.sub(r"[^A-Za-z0-9._-]+", "_", self.inputs.topic.strip())
        safe_topic = safe_topic.strip("_") or "topic"
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        return f"{timestamp}_{safe_topic}"

    @staticmethod
    def _make_unique_run_dir(path: Path) -> Path:
        if not path.exists():
            return path
        counter = 1
        while True:
            candidate = path.parent / f"{path.name}_{counter}"
            if not candidate.exists():
                return candidate
            counter += 1

    @staticmethod
    def _write_json(path: Path, payload: object) -> str:
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    @staticmethod
    def _write_text(path: Path, payload: str) -> str:
        path.write_text(payload, encoding="utf-8")
        return str(path)
