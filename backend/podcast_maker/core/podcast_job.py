"""Production podcast generation through the YAML pipeline engine, with per-stage recovery.

The plan is frozen when the podcast is created: the exact pipeline YAML is saved in the
episode's bucket folder (`urls["pipeline"]`, the first checkpoint) and the resolved inputs
are saved in the podcast record's config. A run - first or a retry - reads only those, never
the pipeline file on disk, so editing a pipeline can't change an episode that is mid-recovery.

Checkpoints are stage ids (one artifact URL per stage, from the stage's declared output file),
then `audio` and `transcript`. Resume skips every stage that already has an artifact and seeds
the later stages from the saved output. Audio/transcripts are a fixed tail after the pipeline;
the script they voice is the final stage's output.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.request import urlopen

from dotenv import load_dotenv

from podcast_maker.core.formats import PIPELINE_URL_KEY, artifact_file_names, parse_and_validate
from podcast_maker.core.hosts_config import get_host_profile
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.paths import BACKEND_ROOT
from podcast_maker.engine.executor import run_pipeline
from podcast_maker.engine.pipeline_meta import final_stage_id, stage_output_files
from podcast_maker.services.GoogleTTS import GoogleTTS
from podcast_maker.services.storage_provider import StorageProvider
from podcast_maker.services.transcript_formatter import format_transcript_to_json, format_transcript_to_vtt

load_dotenv(dotenv_path=BACKEND_ROOT / ".env")
logger = get_logger()


@dataclass
class PodcastConfig:
    """The podcast record's config: what to make. `format` is a pipeline id; `inputs` are the
    pipeline's resolved inputs, frozen at creation (see formats.build_inputs)."""

    topic: str
    host_ids: List[str] = field(default_factory=list)
    format: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)


def _load_text_from_url(url: str) -> str:
    with urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8")


def _stage_outputs_from_artifact(stage: dict[str, Any], artifact_text: str) -> dict[str, Any]:
    """Rebuild the {output_name: value} dict a stage would have produced from its saved artifact."""
    response = stage["response"]
    value: Any = json.loads(artifact_text) if response.get("kind") == "json" else artifact_text
    outputs: dict[str, Any] = {}
    for name, spec in stage["outputs"].items():
        source = spec["source"]
        if source in ("response", "response.aggregate"):
            outputs[name] = value
        elif source.startswith("response.") and source != "response.items" and isinstance(value, dict):
            outputs[name] = value.get(source.split(".", 1)[1])
        else:
            outputs[name] = None  # e.g. per-item lists are not persisted as artifacts
    return outputs


class PodcastJob:
    def __init__(self, config: PodcastConfig, storage_provider: StorageProvider, user_id: str = "system"):
        self.config = config
        self.storage_provider = storage_provider
        self.user_id = user_id
        self.google_tts = GoogleTTS(os.getenv("GOOGLE_TTS_KEY"))

    def _build_voice_dict(self) -> Dict[str, str]:
        """Voice per HOST_n placeholder, based on the selected hosts."""
        return {f"HOST_{i}": get_host_profile(host_id).voice_id for i, host_id in enumerate(self.config.host_ids, 1)}

    def _upload(self, local_path: Path, file_name: str) -> str:
        return self.storage_provider.save_file(str(local_path), file_name)

    def run(
        self,
        existing_urls: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[str, Dict[str, str]], None]] = None,
    ) -> dict:
        """Run (or resume) the podcast. Returns artifact key -> URL/path."""
        file_urls: Dict[str, str] = dict(existing_urls or {})

        def notify(checkpoint: str) -> None:
            if progress_callback:
                progress_callback(checkpoint, dict(file_urls))

        if not file_urls.get(PIPELINE_URL_KEY):
            raise RuntimeError("Podcast has no saved pipeline (urls['pipeline']); it cannot be run or recovered")
        pipeline_data = parse_and_validate(_load_text_from_url(file_urls[PIPELINE_URL_KEY]))
        stages = {stage["id"]: stage for stage in pipeline_data["stages"]}
        file_names = artifact_file_names(pipeline_data)
        output_files = stage_output_files(pipeline_data)  # {stage_id: run-relative output file}
        script_stage = final_stage_id(pipeline_data)
        if not script_stage:
            raise RuntimeError(f"Pipeline {pipeline_data['id']!r} writes no output file to voice")

        with tempfile.TemporaryDirectory(prefix="podcast_") as tmp:
            temp_dir = Path(tmp)
            run_dir = temp_dir / "run"
            run_dir.mkdir()

            # Stages whose artifact already exists are skipped; their saved output seeds later stages.
            run_stages: set[str] = set()
            mock_outputs: dict[str, dict[str, Any]] = {}
            script_text: Optional[str] = None
            for stage_id in stages:
                if stage_id not in file_names:
                    run_stages.add(stage_id)
                elif file_urls.get(stage_id):
                    artifact_text = _load_text_from_url(file_urls[stage_id])
                    mock_outputs[stage_id] = _stage_outputs_from_artifact(stages[stage_id], artifact_text)
                    if stage_id == script_stage:
                        script_text = artifact_text
                    logger.info("stage_skipped stage=%s url=%s", stage_id, file_urls[stage_id])
                else:
                    run_stages.add(stage_id)

            def on_stage_complete(stage_id: str, outputs: dict[str, Any], result: dict[str, Any]) -> None:
                if stage_id not in file_names:
                    return
                file_urls[stage_id] = self._upload(run_dir / output_files[stage_id], file_names[stage_id])
                logger.info("stage_done stage=%s url=%s", stage_id, file_urls[stage_id])
                notify(stage_id)

            if run_stages:
                run_pipeline(
                    pipeline_data,
                    dict(self.config.inputs),
                    root=BACKEND_ROOT,
                    run_dir=run_dir,
                    user_id=self.user_id,
                    run_stages=run_stages,
                    mock_outputs=mock_outputs,
                    on_stage_complete=on_stage_complete,
                )
                if script_stage in run_stages:
                    script_text = (run_dir / output_files[script_stage]).read_text(encoding="utf-8")

            if script_text is None:
                raise RuntimeError(f"Stage {script_stage!r} produced no script to voice")

            audio, transcript_segments = self.google_tts.text_to_speech_with_timestamps(
                script_text, voice_dict=self._build_voice_dict()
            )

            audio_file = temp_dir / "podcast_audio.mp3"
            audio.export(audio_file, format="mp3")
            file_urls["audio"] = self._upload(audio_file, "podcast_audio.mp3")
            notify("audio")

            for key, file_name, payload in (
                ("transcript", "transcript.json", format_transcript_to_json(transcript_segments)),
                ("transcript_vtt", "transcript.vtt", format_transcript_to_vtt(transcript_segments)),
            ):
                artifact_file = temp_dir / file_name
                artifact_file.write_text(payload, encoding="utf-8")
                file_urls[key] = self._upload(artifact_file, file_name)
                logger.info("transcript_done key=%s url=%s", key, file_urls[key])
            notify("transcript")

        return file_urls
