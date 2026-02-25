# prompt_manager.py
import json
from typing import Dict, Any, List, Optional

from podcast_maker.core.paths import PROMPTS_DIR
from podcast_maker.core.hosts_config import format_hosts_for_prompt

# class PodcastConfig:
#     """User preferences for podcast generation"""
#     def __init__(
#         self,
#         format: str = "dialogue",  # dialogue/monologue/debate/interview
#         num_hosts: int = 2,
#         duration_minutes: int = 30,
#         tone: str = "conversational",
#         depth: str = "medium",
#         focus_areas: list = None,
#         target_audience: str = "general"
#     ):
#         self.format = format
#         self.num_hosts = num_hosts
#         self.duration_minutes = duration_minutes
#         self.tone = tone
#         self.depth = depth
#         self.focus_areas = focus_areas or []
#         self.target_audience = target_audience


class PromptManager:
    """Responsible for building prompts based on user preferences"""
    
    def __init__(self, user_topic: str, host_ids: Optional[List[str]] = None):
        self.user_topic = user_topic
        self.host_ids = host_ids or ["sarah_curious", "mike_expert"]  # Default hosts
        self.prompts_dir = PROMPTS_DIR
    
    def get_architect_prompt(self) -> str:
        """Build architect prompt"""
        prompt = self._load_base_prompt('architect.md')
        prompt = prompt.replace("{{USER_TOPIC}}", self.user_topic)
        return prompt
    
    def get_researcher_prompt(self, segment: Dict[str, Any]) -> str:
        """Build researcher prompt for a specific segment"""
        prompt = self._load_base_prompt('researcher.md')
        segment_name = segment.get("segment_name", "Unknown Segment")
            
        # Convert entire segment to JSON string
        segment_json = json.dumps(segment, ensure_ascii=False, indent=2)
        
        # Optional: extract these for display/override purposes
        target_word_count = segment.get("target_word_count", "N/A")
        depth_level = segment.get("depth_level", "MEDIUM")
        
        # Replace placeholders
        prompt = prompt.replace("{{SEGMENT_JSON}}", segment_json)
        prompt = prompt.replace("{{TARGET_WORD_COUNT}}", str(target_word_count))
        prompt = prompt.replace("{{DEPTH_LEVEL}}", str(depth_level))
        return prompt
    
    def get_outliner_prompt(self, blueprint: Dict, research: str, topic: str) -> str:
        """Build outliner prompt"""
        import json
        
        prompt = self._load_base_prompt('outliner.md')
        prompt = prompt.replace("{{BLUEPRINT}}", json.dumps(blueprint))
        prompt = prompt.replace("{{RESEARCH}}", json.dumps(research))
        prompt = prompt.replace("{{TOPIC}}", topic)
        
        return prompt
    
    def get_scriptwriter_prompt(self, outline: Dict, research: str, previous_scenes: str) -> str:
        """Build scriptwriter prompt with host information"""
        
        prompt = self._load_base_prompt('scriptwriter.md')
        
        # Inject host profiles
        hosts_info = format_hosts_for_prompt(self.host_ids)
        prompt = prompt.replace("{{HOSTS_PROFILES}}", hosts_info)
        
        prompt = prompt.replace("{{OUTLINE_JSON}}", json.dumps(outline))
        prompt = prompt.replace("{{RESEARCH_TEXT}}", research)
        prompt = prompt.replace("{{PREVIOUS_SCENES}}", previous_scenes)
        
        return prompt
    
    def _load_base_prompt(self, filename: str) -> str:
        """Load base prompt file"""
        filepath = self.prompts_dir / filename
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()