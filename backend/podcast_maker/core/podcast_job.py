"""Production podcast generation through the YAML pipeline engine.

`PodcastJob.process_topic` has the same contract the API layer relies on:
artifact keys (blueprint, research, outline, script, audio, transcript, transcript_vtt),
progress checkpoints after each of them, and resume from `existing_urls` (stages whose
artifact URL already exists are skipped and their saved output seeds the later stages).
The four text stages run as the `duo_long` / `solo_short` pipeline from
resources/pipelines; TTS and transcripts happen afterwards, as before.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.request import urlopen

import yaml
from dotenv import load_dotenv

from podcast_maker.core.hosts_config import format_hosts_for_prompt, get_host_profile
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.paths import BACKEND_ROOT, PIPELINES_DIR
from podcast_maker.engine.executor import run_pipeline
from podcast_maker.engine.inputs import resolve_inputs
from podcast_maker.engine.validate_pipeline import validate_pipeline_data
from podcast_maker.services.GoogleTTS import GoogleTTS
from podcast_maker.services.storage_provider import StorageProvider
from podcast_maker.services.transcript_formatter import format_transcript_to_json, format_transcript_to_vtt

load_dotenv(dotenv_path=BACKEND_ROOT / ".env")
logger = get_logger()

FORMAT_TO_PIPELINE = {"dialogue": "duo_long", "solo": "solo_short"}

# (pipeline stage id, artifact key / checkpoint, uploaded file name), in execution order.
STAGE_ARTIFACTS = (
    ("architect", "blueprint", "blueprint.json"),
    ("researcher", "research", "research.md"),
    ("outliner", "outline", "outline.json"),
    ("scriptwriter", "script", "script.txt"),
)


@dataclass
class PodcastConfig:
    """User preferences for podcast generation"""
    topic: str
    host_ids: List[str] = field(default_factory=lambda: ["sarah_curious", "mike_expert"])
    format: Optional[str] = None
    duration_minutes: int = 30
    tone: str = "conversational"
    target_audience: str = "general"

    @property
    def normalized_host_ids(self) -> List[str]:
        return self.host_ids or ["sarah_curious", "mike_expert"]

    @property
    def effective_format(self) -> str:
        if self.format:
            return self.format.strip().lower()
        if len(self.normalized_host_ids) == 1:
            return "solo"
        return "dialogue"

    @property
    def hosts(self) -> Dict[str, str]:
        return {f"HOST_{i}": host_id for i, host_id in enumerate(self.normalized_host_ids, start=1)}


def _response_file(stage: dict[str, Any]) -> str:
    response = stage["response"]
    return response["file"] if stage["execution"] == "single" else response["aggregate_file"]


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
    def __init__(self, podcast_config: PodcastConfig, storage_provider: StorageProvider, user_id: str = "system"):
        self.config = podcast_config
        self.user_topic = podcast_config.topic
        self.host_ids = podcast_config.normalized_host_ids
        self.storage_provider = storage_provider
        self.user_id = user_id
        self.google_tts = GoogleTTS(os.getenv("GOOGLE_TTS_KEY"))

    def _load_pipeline(self) -> dict[str, Any]:
        pipeline_id = FORMAT_TO_PIPELINE.get(self.config.effective_format, FORMAT_TO_PIPELINE["dialogue"])
        path = PIPELINES_DIR / pipeline_id / "pipeline.yaml"
        pipeline_data = yaml.safe_load(path.read_text(encoding="utf-8"))
        validate_pipeline_data(pipeline_data, BACKEND_ROOT)
        return pipeline_data

    def _pipeline_inputs(self, pipeline_data: dict[str, Any]) -> dict[str, Any]:
        raw = {
            "topic": self.user_topic,
            "host_profiles": format_hosts_for_prompt(self.host_ids),
            "host_name": get_host_profile(self.host_ids[0]).name,
        }
        return resolve_inputs(pipeline_data.get("inputs") or {}, raw)

    def _build_voice_dict(self) -> Dict[str, str]:
        """Voice per HOST_n placeholder, based on the selected hosts."""
        return {f"HOST_{i}": get_host_profile(host_id).voice_id for i, host_id in enumerate(self.host_ids, 1)}

    def _safe_folder_name(self) -> str:
        folder_name = "".join(x for x in self.user_topic if x.isalnum() or x in "._- ").strip().replace(" ", "_")
        return folder_name or "podcast"

    def _upload(self, local_path: Path, folder_name: str, file_name: str) -> str:
        return self.storage_provider.save_file(str(local_path), f"{folder_name}/{file_name}")

    def _save_text_artifact(self, temp_dir: Path, folder_name: str, file_name: str, payload: str) -> str:
        artifact_file = temp_dir / file_name
        artifact_file.write_text(payload, encoding="utf-8")
        return self._upload(artifact_file, folder_name, file_name)

    def process_topic(
        self,
        existing_urls: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[str, Dict[str, str]], None]] = None,
    ) -> dict:
        """Run (or resume) the whole podcast generation. Returns artifact key -> URL/path."""
        folder_name = self._safe_folder_name()
        file_urls: Dict[str, str] = dict(existing_urls or {})

        def notify(checkpoint: str) -> None:
            if progress_callback:
                progress_callback(checkpoint, dict(file_urls))

        pipeline_data = self._load_pipeline()
        stages = {stage["id"]: stage for stage in pipeline_data["stages"]}
        artifact_by_stage = {stage_id: (key, file_name) for stage_id, key, file_name in STAGE_ARTIFACTS}

        with tempfile.TemporaryDirectory(prefix=f"podcast_{folder_name}_") as tmp:
            temp_dir = Path(tmp)
            run_dir = temp_dir / "run"
            run_dir.mkdir()

            # Stages whose artifact already exists are skipped; their saved output seeds later stages.
            run_stages: set[str] = set()
            mock_outputs: dict[str, dict[str, Any]] = {}
            for stage_id, key, _ in STAGE_ARTIFACTS:
                if file_urls.get(key):
                    mock_outputs[stage_id] = _stage_outputs_from_artifact(
                        stages[stage_id], _load_text_from_url(file_urls[key])
                    )
                    logger.info("agent_skipped agent=%s url=%s", stage_id, file_urls[key])
                else:
                    run_stages.add(stage_id)

            def on_stage_complete(stage_id: str, outputs: dict[str, Any], result: dict[str, Any]) -> None:
                key, file_name = artifact_by_stage[stage_id]
                file_urls[key] = self._upload(run_dir / _response_file(stages[stage_id]), folder_name, file_name)
                logger.info("agent_done agent=%s url=%s", stage_id, file_urls[key])
                notify(key)

            if run_stages:
                run_pipeline(
                    pipeline_data,
                    self._pipeline_inputs(pipeline_data),
                    root=BACKEND_ROOT,
                    run_dir=run_dir,
                    user_id=self.user_id,
                    run_stages=run_stages,
                    mock_outputs=mock_outputs,
                    on_stage_complete=on_stage_complete,
                )

            if "scriptwriter" in run_stages:
                script = (run_dir / _response_file(stages["scriptwriter"])).read_text(encoding="utf-8")
            else:
                script = _load_text_from_url(file_urls["script"])

            voice_dict = self._build_voice_dict()
            audio, transcript_segments = self.google_tts.text_to_speech_with_timestamps(script, voice_dict=voice_dict)

            audio_file = temp_dir / "podcast_audio.mp3"
            audio.export(audio_file, format="mp3")
            file_urls["audio"] = self._upload(audio_file, folder_name, "podcast_audio.mp3")
            notify("audio")

            file_urls["transcript"] = self._save_text_artifact(
                temp_dir, folder_name, "transcript.json", format_transcript_to_json(transcript_segments)
            )
            logger.info("transcript_done format=json url=%s", file_urls["transcript"])

            file_urls["transcript_vtt"] = self._save_text_artifact(
                temp_dir, folder_name, "transcript.vtt", format_transcript_to_vtt(transcript_segments)
            )
            logger.info("transcript_done format=vtt url=%s", file_urls["transcript_vtt"])
            notify("transcript")

        return file_urls
