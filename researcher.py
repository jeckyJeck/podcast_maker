import json
from pathlib import Path
from google import genai
from google.genai import types

from prompt_manager import PromptManager


class Researcher:
    def __init__(self, client: genai.Client, prompt_manager: PromptManager):
        self.client = client
        self.model = "gemini-2.5-flash"
        self.prompt_manager = prompt_manager
        self.prompt_path = Path('prompts/researcher.md')
    
    def conduct_research(self, blueprint: dict) -> dict:
        """
        Takes the blueprint and performs deep research for each segment using Google Search.
        Returns a dictionary mapping segment names to their research reports (as markdown text).
        """
        search_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        
        system_prompt = self.prompt_manager.get_researcher_prompt()
        
        research_results = []
        
        for segment in blueprint.get("segments", []):
            segment_name = segment.get("segment_name", "Unknown Segment")
            current_prompt = self.prompt_manager.get_researcher_prompt(segment)

            print(f"--- Researching: {segment_name} ---")
            
            response = self.client.models.generate_content(
                model=self.model,
                contents=current_prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="text/plain",  
                    temperature=0.7,
                    tools=[search_tool]
                )
            )
            
            # Store the markdown text directly
            research_results.append(response.text)
            
            print(f"    ✓ Research completed ({len(response.text.split())} words)")
        
        return "\n".join(research_results)