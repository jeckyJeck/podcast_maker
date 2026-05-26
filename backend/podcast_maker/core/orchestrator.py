import os
import json
import tempfile
from urllib.request import urlopen
from pathlib import Path
from typing import Callable, Dict, Optional

from dotenv import load_dotenv

from podcast_maker.core.architect import Architect
from podcast_maker.core.outliner import Outliner
from podcast_maker.core.paths import BACKEND_ROOT, OUTPUT_DIR
from podcast_maker.core.prompt_manager import PromptManager, PodcastConfig
from podcast_maker.core.researcher import Researcher
from podcast_maker.core.scriptwriter import ScriptWriter
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.hosts_config import get_host_profile
from podcast_maker.services.GoogleTTS import GoogleTTS
from podcast_maker.services.llm_provider_factory import build_llm_provider
from podcast_maker.services.local_storage_provider import LocalStorageProvider
from podcast_maker.services.storage_provider import StorageProvider
from podcast_maker.services.transcript_formatter import (
    format_transcript_to_json, 
    format_transcript_to_vtt
)


load_dotenv(dotenv_path=BACKEND_ROOT / ".env")
logger = get_logger()

#google voices
FEMALE_VOICE_ID_GOOGLE = "en-US-Studio-O"
MALE_VOICE_ID_GOOGLE = "en-US-Studio-Q"

class PodcastMakerOrchestrator:
    def __init__(
        self, 
        podcast_config: PodcastConfig,
        storage_provider: StorageProvider,
    ):
        self.config = podcast_config
        self.user_topic = podcast_config.topic
        self.host_ids = podcast_config.normalized_host_ids
        self.podcast_config = podcast_config
        
        self.llm_provider = build_llm_provider("gemini")
        
        prompt_manager = PromptManager(self.podcast_config)
        self.architect = Architect(self.llm_provider, prompt_manager)
        self.researcher = Researcher(self.llm_provider, prompt_manager)
        self.outliner = Outliner(self.llm_provider, prompt_manager)
        self.scriptwriter = ScriptWriter(self.llm_provider, prompt_manager)
        self.google_tts = GoogleTTS(os.getenv("GOOGLE_TTS_KEY"))
        self.storage_provider = storage_provider

    def _get_unique_output_dir(self, base_name: str) -> Path:
        """Create a unique output directory."""
        base_path = OUTPUT_DIR
        target_path = base_path / base_name
        if not target_path.exists():
            target_path.mkdir(parents=True)
            return target_path
        counter = 1
        while True:
            new_path = base_path / f"{base_name}_{counter}"
            if not new_path.exists():
                new_path.mkdir(parents=True)
                return new_path
            counter += 1

    def _get_temp_folder(self, base_name: str) -> Path:
        unique_dir = Path(tempfile.mkdtemp(prefix=f"podcast_{base_name}_"))
        return unique_dir
    
    def _build_voice_dict(self) -> Dict[str, str]:
        """Build voice dictionary for TTS based on selected hosts"""
        voice_dict = {}
        for i, host_id in enumerate(self.host_ids, 1):
            profile = get_host_profile(host_id)
            # Map HOST_1, HOST_2, etc. to the voice_id directly
            voice_dict[f"HOST_{i}"] = profile.voice_id
        return voice_dict

    def _build_storage_path(self, folder_name: str, file_name: str) -> str:
        return f"{folder_name}/{file_name}"

    def _safe_folder_name(self) -> str:
        folder_name = "".join(x for x in self.user_topic if x.isalnum() or x in "._- ").strip().replace(" ", "_")
        return folder_name or "podcast"

    def _load_text_from_url(self, url: str) -> str:
        with urlopen(url, timeout=60) as response:
            return response.read().decode("utf-8")

    def _load_json_from_url(self, url: str) -> dict:
        return json.loads(self._load_text_from_url(url))

    def _save_json_artifact(self, temp_dir: Path, folder_name: str, file_name: str, payload: dict) -> str:
        artifact_file = temp_dir / file_name
        with open(artifact_file, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
        return self.storage_provider.save_file(str(artifact_file), self._build_storage_path(folder_name, file_name))

    def _save_text_artifact(self, temp_dir: Path, folder_name: str, file_name: str, payload: str) -> str:
        artifact_file = temp_dir / file_name
        with open(artifact_file, 'w', encoding='utf-8') as f:
            f.write(payload)
        return self.storage_provider.save_file(str(artifact_file), self._build_storage_path(folder_name, file_name))

    def process_topic(
        self,
        existing_urls: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[str, Dict[str, str]], None]] = None,
    ) -> dict:
        """
        Orchestrates the entire podcast generation process.
        Returns a dictionary with file names and their URLs/paths.
        """
        user_topic = self.user_topic
        folder_name = self._safe_folder_name()
        temp_dir = self._get_temp_folder(folder_name)
        file_urls: Dict[str, str] = dict(existing_urls or {})

        def notify(checkpoint: str) -> None:
            if progress_callback:
                progress_callback(checkpoint, dict(file_urls))

        if file_urls.get("blueprint"):
            blueprint = self._load_json_from_url(file_urls["blueprint"])
            logger.info("agent_skipped agent=architect url=%s", file_urls["blueprint"])
        else:
            blueprint = self.architect.generate_blueprint(user_topic)
            file_urls["blueprint"] = self._save_json_artifact(temp_dir, folder_name, "blueprint.json", blueprint)
            logger.info("agent_done agent=architect url=%s", file_urls["blueprint"])
            notify("blueprint")

        if file_urls.get("research"):
            research = self._load_text_from_url(file_urls["research"])
            logger.info("agent_skipped agent=researcher url=%s", file_urls["research"])
        else:
            research = self.researcher.conduct_research(blueprint)
            file_urls["research"] = self._save_text_artifact(temp_dir, folder_name, "research.md", research)
            logger.info("agent_done agent=researcher url=%s", file_urls["research"])
            notify("research")

        if file_urls.get("outline"):
            outline = self._load_json_from_url(file_urls["outline"])
            logger.info("agent_skipped agent=outliner url=%s", file_urls["outline"])
        else:
            outline = self.outliner.create_outline(blueprint, research, user_topic)
            file_urls["outline"] = self._save_json_artifact(temp_dir, folder_name, "outline.json", outline)
            logger.info("agent_done agent=outliner url=%s", file_urls["outline"])
            notify("outline")

        if file_urls.get("script"):
            script = self._load_text_from_url(file_urls["script"])
            logger.info("agent_skipped agent=scriptwriter url=%s", file_urls["script"])
        else:
            script = self.scriptwriter.write_script(outline, research, user_topic)
            file_urls["script"] = self._save_text_artifact(temp_dir, folder_name, "script.txt", script)
            logger.info("agent_done agent=scriptwriter url=%s", file_urls["script"])
            notify("script")

        voice_dict = self._build_voice_dict()
        audio, transcript_segments = self.google_tts.text_to_speech_with_timestamps(script, voice_dict=voice_dict)

        audio_file = temp_dir / "podcast_audio.mp3"
        audio.export(audio_file, format="mp3")
        file_urls["audio"] = self.storage_provider.save_file(str(audio_file), self._build_storage_path(folder_name, "podcast_audio.mp3"))
        notify("audio")

        transcript_json = format_transcript_to_json(transcript_segments)
        file_urls["transcript"] = self._save_text_artifact(temp_dir, folder_name, "transcript.json", transcript_json)
        logger.info("transcript_done format=json url=%s", file_urls["transcript"])

        transcript_vtt = format_transcript_to_vtt(transcript_segments)
        file_urls["transcript_vtt"] = self._save_text_artifact(temp_dir, folder_name, "transcript.vtt", transcript_vtt)
        logger.info("transcript_done format=vtt url=%s", file_urls["transcript_vtt"])
        notify("transcript")
        
        return file_urls



if __name__ == "__main__":
    user_input = "claude code skills"

    storage_provider = LocalStorageProvider()
    config = PodcastConfig(
        topic=user_input,
        host_ids=["sarah_curious", "mike_expert"],
        format="dialogue",
    )
    orchestrator = PodcastMakerOrchestrator(config, storage_provider)
    file_urls = orchestrator.process_topic()
    
    print(f"--- Done! ---")
    print("Files saved:")
    for file_name, url in file_urls.items():
        print(f"  {file_name}: {url}")
