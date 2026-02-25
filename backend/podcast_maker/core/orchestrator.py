import os
import json
import tempfile
from pathlib import Path
from typing import List, Optional, Dict
from pydub import AudioSegment

from dotenv import load_dotenv
from google import genai

from podcast_maker.core.architect import Architect
from podcast_maker.core.outliner import Outliner
from podcast_maker.core.paths import BACKEND_ROOT, OUTPUT_DIR
from podcast_maker.core.prompt_manager import PromptManager
from podcast_maker.core.researcher import Researcher
from podcast_maker.core.rate_limiter import RateLimiter
from podcast_maker.core.scriptwriter import ScriptWriter
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.hosts_config import get_host_profile
from podcast_maker.services.GoogleTTS import GoogleTTS, FEMALE_VOICE_CHIRPHD, MALE_VOICE_CHIRPHD
from podcast_maker.services.local_storage_provider import LocalStorageProvider
from podcast_maker.services.storage_provider import StorageProvider
from podcast_maker.services.gemini_adapter import GeminiAdapter
from podcast_maker.services.transcript_formatter import (
    format_transcript_to_json, 
    format_transcript_to_vtt
)


load_dotenv(dotenv_path=BACKEND_ROOT / ".env")
logger = get_logger()

#google voices
FEMALE_VOICE_ID_GOOGLE = "en-US-Studio-O"
MALE_VOICE_ID_GOOGLE = "en-US-Studio-Q"

ITERATIVE_MODEL_RATE_LIMITER = RateLimiter(max_requests=4, period_seconds=60)

class PodcastMakerOrchestrator:
    def __init__(
        self, 
        user_topic: str, 
        storage_provider: StorageProvider,
        host_ids: Optional[List[str]] = None
    ):
        self.user_topic = user_topic
        self.host_ids = host_ids or ["sarah_curious", "mike_expert"]  # Default hosts
        
        # Create Gemini client and wrap it with adapter (with rate limiting)
        client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        self.llm_provider = GeminiAdapter(client, rate_limiter=ITERATIVE_MODEL_RATE_LIMITER)
        
        prompt_manager = PromptManager(user_topic, self.host_ids)
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
        
    def process_topic(self, user_topic: str) -> dict:
        """
        Orchestrates the entire podcast generation process.
        Returns a dictionary with file names and their URLs/paths.
        """
        # Create temporary working directory
        folder_name = "".join(x for x in user_topic if x.isalnum() or x in "._- ").strip().replace(" ", "_")
        temp_dir = self._get_temp_folder(folder_name)
        
        file_urls = {}
        
        # Step 1: Generate blueprint
        blueprint = self.architect.generate_blueprint(user_topic)
        blueprint_file = temp_dir / "blueprint.json"
        with open(blueprint_file, 'w', encoding='utf-8') as f:
            json.dump(blueprint, f, indent=4, ensure_ascii=False)
        file_urls["blueprint"] = self.storage_provider.save_file(str(blueprint_file), f"{folder_name}/blueprint.json")
        logger.info("agent_done agent=architect url=%s", file_urls["blueprint"])
        
        # Step 2: Conduct research
        research = self.researcher.conduct_research(blueprint)
        research_file = temp_dir / "research.md"
        with open(research_file, 'w', encoding='utf-8') as f:
            f.write(research)
        file_urls["research"] = self.storage_provider.save_file(str(research_file), f"{folder_name}/research.md")
        logger.info("agent_done agent=researcher url=%s", file_urls["research"])
        
        # Step 3: Create outline
        outline = self.outliner.create_outline(blueprint, research, user_topic)
        outline_file = temp_dir / "outline.json"
        with open(outline_file, 'w', encoding='utf-8') as f:
            json.dump(outline, f, indent=4, ensure_ascii=False)
        file_urls["outline"] = self.storage_provider.save_file(str(outline_file), f"{folder_name}/outline.json")
        logger.info("agent_done agent=outliner url=%s", file_urls["outline"])

        # Step 4: Write script
        script = self.scriptwriter.write_script(outline, research, user_topic)
        script_file = temp_dir / "script.txt"
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(script)
        file_urls["script"] = self.storage_provider.save_file(str(script_file), f"{folder_name}/script.txt")
        logger.info("agent_done agent=scriptwriter url=%s", file_urls["script"])

        # Step 5: Convert script to audio with timestamps
        voice_dict = self._build_voice_dict()
        audio, transcript_segments = self.google_tts.text_to_speech_with_timestamps(script, voice_dict=voice_dict)
        
        # Save audio
        audio_file = temp_dir / "podcast_audio.mp3"
        audio.export(audio_file, format="mp3")
        file_urls["audio"] = self.storage_provider.save_file(str(audio_file), f"{folder_name}/podcast_audio.mp3")
        
        # Save transcript as JSON
        transcript_json = format_transcript_to_json(transcript_segments)
        transcript_json_file = temp_dir / "transcript.json"
        with open(transcript_json_file, 'w', encoding='utf-8') as f:
            f.write(transcript_json)
        file_urls["transcript"] = self.storage_provider.save_file(str(transcript_json_file), f"{folder_name}/transcript.json")
        logger.info("transcript_done format=json url=%s", file_urls["transcript"])
        
        # Save transcript as WebVTT
        transcript_vtt = format_transcript_to_vtt(transcript_segments)
        transcript_vtt_file = temp_dir / "transcript.vtt"
        with open(transcript_vtt_file, 'w', encoding='utf-8') as f:
            f.write(transcript_vtt)
        file_urls["transcript_vtt"] = self.storage_provider.save_file(str(transcript_vtt_file), f"{folder_name}/transcript.vtt")
        logger.info("transcript_done format=vtt url=%s", file_urls["transcript_vtt"])

        
        return file_urls



if __name__ == "__main__":
    user_input = "claude code skills"
    
    storage_provider = LocalStorageProvider()
    orchestrator = PodcastMakerOrchestrator(user_input, storage_provider, ["sarah_curious", "mike_expert"])
    file_urls = orchestrator.process_topic(user_input)
    
    print(f"--- Done! ---")
    print("Files saved:")
    for file_name, url in file_urls.items():
        print(f"  {file_name}: {url}")
