import json
from pathlib import Path
from google import genai
from google.genai import types

from prompt_manager import PromptManager


class Architect:
    def __init__(self, client: genai.Client, prompt_manager: PromptManager):
        self.client = client
        self.model = "gemini-2.5-flash"
        self.prompt_manager = prompt_manager
    
    def generate_blueprint(self, user_topic: str) -> dict:
        """Generate the blueprint for a given topic."""
        system_prompt = self.prompt_manager.get_architect_prompt()
        
        print(f"--- Generating blueprint for: {user_topic} ---")
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=system_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7
            )
        )
        
        try:
            blueprint_data = json.loads(response.text)
            return blueprint_data
        except json.JSONDecodeError:
            print("Error: Model did not return valid JSON.")
            return {"error": "Invalid JSON", "raw": response.text}
