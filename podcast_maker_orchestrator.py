import os
import json
from dotenv import load_dotenv
from pathlib import Path
from google import genai
from architect import Architect
from prompt_manager import PromptManager
from researcher import Researcher
from outliner import Outliner
from scriptwriter import ScriptWriter
from GoogleTTS import *
from storage_provider import StorageProvider
from local_storage_provider import LocalStorageProvider
import tempfile


load_dotenv()

#google voices
FEMALE_VOICE_ID_GOOGLE = "en-US-Studio-O"
MALE_VOICE_ID_GOOGLE = "en-US-Studio-Q"

class PodcastMakerOrchestrator:
    def __init__(self, user_topic: str, storage_provider: StorageProvider):
        self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        prompt_manager = PromptManager(user_topic)
        self.architect = Architect(self.client, prompt_manager)
        self.researcher = Researcher(self.client, prompt_manager)
        self.outliner = Outliner(self.client, prompt_manager)
        self.scriptwriter = ScriptWriter(self.client, prompt_manager)
        self.google_tts = GoogleTTS(os.getenv("GOOGLE_TTS_KEY"))
        self.storage_provider = storage_provider
        

    def _get_unique_output_dir(self, base_name: str) -> Path:
        """Create a unique output directory."""
        base_path = Path("output")
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
        
        # Step 2: Conduct research
        research = self.researcher.conduct_research(blueprint)
        research_file = temp_dir / "research.md"
        with open(research_file, 'w', encoding='utf-8') as f:
            f.write(research)
        file_urls["research"] = self.storage_provider.save_file(str(research_file), f"{folder_name}/research.md")
        
        # Step 3: Create outline
        outline = self.outliner.create_outline(blueprint, research, user_topic)
        outline_file = temp_dir / "outline.json"
        with open(outline_file, 'w', encoding='utf-8') as f:
            json.dump(outline, f, indent=4, ensure_ascii=False)
        file_urls["outline"] = self.storage_provider.save_file(str(outline_file), f"{folder_name}/outline.json")

        # Step 4: Write script
        script = self.scriptwriter.write_script(outline, research, user_topic)
        script_file = temp_dir / "script.txt"
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(script)
        file_urls["script"] = self.storage_provider.save_file(str(script_file), f"{folder_name}/script.txt")

        # Step 5: Convert script to audio
        audio = self.google_tts.text_to_speech_not_SSML(script, voice_dict={
            "HOST_1": FEMALE_VOICE_CHIRPHD,
              "HOST_2": MALE_VOICE_CHIRPHD
              })
        audio_file = temp_dir / "podcast_audio.mp3"
        audio.export(audio_file, format="mp3")
        file_urls["audio"] = self.storage_provider.save_file(str(audio_file), f"{folder_name}/podcast_audio.mp3")
        
        return file_urls



if __name__ == "__main__":
    user_input = ""
    
    storage_provider = LocalStorageProvider()
    orchestrator = PodcastMakerOrchestrator(user_input, storage_provider)
    file_urls = orchestrator.process_topic(user_input)
    
    print(f"--- Done! ---")
    print("Files saved:")
    for file_name, url in file_urls.items():
        print(f"  {file_name}: {url}")
