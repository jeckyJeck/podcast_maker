from pathlib import Path
from typing import Optional
from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.prompt_manager import PromptManager
from podcast_maker.services.llm_provider import LLMProvider

logger = get_logger()

class ScriptWriter:
    def __init__(
        self,
        llm_provider: LLMProvider,
        prompt_manager: PromptManager,
    ):
        self.llm_provider = llm_provider
        self.model = "gemini-2.5-flash"
        self.prompt_manager = prompt_manager
    
    def write_script(self, outline: dict, research: str, topic: str) -> str:
        """
        Takes the outline and research data to write the podcast script.
        """        
        print(f"--- Writing script for: {topic} ---")

        current_script = "--- This is Scene 1 - start with the opening ---\n\n"

        prompt_tokens = 0
        response_tokens = 0
        total_tokens = 0

        for scene in outline.get("scenes", []):
            scene_num = scene.get("scene_number", "-1")

            full_prompt = self.prompt_manager.get_scriptwriter_prompt(outline, research, current_script)
            
            print(f"--- Writing scene: {scene_num} ---")

            llm_response = self.llm_provider.generate_text(
                prompt=full_prompt,
                model=self.model,
                temperature=0.8,
                metadata={"stage": "scriptwriter", "scene": scene_num, "topic": topic}
            )
            
            current_script += llm_response.text + "\n"
            current_script += f"\n--- End of Scene {scene_num} ---\n\n"

            # Accumulate token usage
            prompt_tokens += llm_response.prompt_tokens
            response_tokens += llm_response.response_tokens
            total_tokens += llm_response.total_tokens

        logger.info("ScriptWriter total usage: prompt_tokens=%d, response_tokens=%d, total_tokens=%d",
                    prompt_tokens, response_tokens, total_tokens)
        return current_script.strip()