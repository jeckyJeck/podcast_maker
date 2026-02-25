from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.prompt_manager import PromptManager
from podcast_maker.services.llm_provider import LLMProvider

logger = get_logger()

class Architect:
    def __init__(self, llm_provider: LLMProvider, prompt_manager: PromptManager):
        self.llm_provider = llm_provider
        self.model = "gemini-2.5-flash"
        self.prompt_manager = prompt_manager
    
    def generate_blueprint(self, user_topic: str) -> dict:
        """Generate the blueprint for a given topic."""
        system_prompt = self.prompt_manager.get_architect_prompt()
        
        print(f"--- Generating blueprint for: {user_topic} ---")
        
        blueprint_data = self.llm_provider.generate_json(
            prompt=system_prompt,
            model=self.model,
            temperature=0.7,
            metadata={"stage": "architect", "topic": user_topic}
        )
        
        return blueprint_data
