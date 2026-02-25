from pathlib import Path
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.prompt_manager import PromptManager
from podcast_maker.services.llm_provider import LLMProvider

logger = get_logger()

class Outliner:
    def __init__(self, llm_provider: LLMProvider, prompt_manager: PromptManager):
        self.llm_provider = llm_provider
        self.model = "gemini-2.5-flash"
        self.prompt_manager = prompt_manager   
    
    def create_outline(self, blueprint: dict, research: str, topic: str) -> dict:
        """
        Takes the blueprint and research data to create a detailed outline.
        """
        system_prompt = self.prompt_manager.get_outliner_prompt(blueprint, research, topic)
        
        print(f"--- Generating outline for: {topic} ---")
        
        outline_data = self.llm_provider.generate_json(
            prompt=system_prompt,
            model=self.model,
            temperature=0.7,
            metadata={"stage": "outliner", "topic": topic}
        )
        
        return outline_data
