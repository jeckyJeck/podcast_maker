import json
from pathlib import Path
from google import genai
from google.genai import types

from prompt_manager import PromptManager

class ScriptWriter:
    def __init__(self, client: genai.Client, prompt_manager: PromptManager):
        self.client = client
        self.model = "gemini-2.5-flash"
        self.prompt_manager = prompt_manager
    
    def write_script(self, outline: dict, research: str, topic: str) -> str:
        """
        Takes the outline and research data to write the podcast script.
        """        
        print(f"--- Writing script for: {topic} ---")

        current_script = ""

        for scene in outline.get("scenes", []):
            scene_num = scene.get("scene_number", "-1")

            full_prompt = self.prompt_manager.get_scriptwriter_prompt(outline, research, current_script)
            
            print(f"--- Writing scene: {scene_num} ---")
            response = self.client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="text/plain",
                    temperature=0.8
                )
            )

            current_script += response.text + "\n"
            current_script += "\n--- End of Scene ---\n\n"
        
        return current_script.strip()