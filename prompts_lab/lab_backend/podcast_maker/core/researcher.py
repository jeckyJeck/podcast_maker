from google.genai import types
from podcast_maker.core.prompt_manager import PromptManager
from podcast_maker.services.llm_provider import LLMProvider

class Researcher:
    def __init__(
        self,
        llm_provider: LLMProvider,
        prompt_manager: PromptManager,
    ):
        self.llm_provider = llm_provider
        self.prompt_manager = prompt_manager
    
    def conduct_research(self, blueprint: dict) -> str:
        """
        Takes the blueprint and performs deep research for each segment using Google Search.
        Returns a string containing all research reports (as markdown text).
        """
        search_tool = types.Tool(
            google_search=types.GoogleSearch()
        )
        
        research_results = ""
        
        for direction in blueprint.get("directions", []):
            direction_name = direction.get("direction_name", "Unknown Direction")
            current_prompt = self.prompt_manager.get_researcher_prompt(direction, research_results)

            print(f"--- Researching: {direction_name} ---")

            llm_response = self.llm_provider.generate_text(
                prompt=current_prompt,
                temperature=0.7,
                tools=[search_tool],
                metadata={"stage": "researcher", "segment": direction_name}
            )
            
            if not llm_response.text:
                print(f"Error: Model did not return any content for segment '{direction_name}'.")
                research_results += f"## {direction_name}\n\nNo research results returned.\n"
                continue
            
            research_results += llm_response.text
            
            word_count = len(llm_response.text.split())
            print(f"    ✓ Research completed ({word_count} words)")

        return research_results
    
    
