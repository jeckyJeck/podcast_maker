import json
from pathlib import Path
from google import genai
from google.genai import types

from prompt_manager import PromptManager


class Outliner:
    def __init__(self, client: genai.Client, prompt_manager: PromptManager):
        self.client = client
        self.model = "gemini-2.5-flash"
        self.prompt_manager = prompt_manager   
    
    def create_outline(self, blueprint: dict, research: str, topic: str) -> dict:
        """
        Takes the blueprint and research data to create a detailed outline.
        """
        system_prompt = self.prompt_manager.get_outliner_prompt(blueprint, research, topic)
        
        print(f"--- Generating outline for: {topic} ---")
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=system_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7
            )
        )
        
        try:
            outline_data = json.loads(response.text)
            return outline_data
        except json.JSONDecodeError:
            print("Error: Model did not return valid JSON.")
            return {"error": "Invalid JSON", "raw": response.text}
