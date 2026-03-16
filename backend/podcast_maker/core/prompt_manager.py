# prompt_manager.py
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, List, Optional

from podcast_maker.core.paths import PROMPTS_DIR
from podcast_maker.core.hosts_config import format_hosts_for_prompt, get_host_profile

@dataclass
class PodcastConfig:
    """User preferences for podcast generation"""
    topic: str
    host_ids: List[str] = field(default_factory=lambda: ["sarah_curious", "mike_expert"])
    format: Optional[str] = None
    duration_minutes: int = 30
    tone: str = "conversational"
    target_audience: str = "general"

    @property
    def normalized_host_ids(self) -> List[str]:
        return self.host_ids or ["sarah_curious", "mike_expert"]

    @property
    def effective_format(self) -> str:
        if self.format:
            return self.format.strip().lower()
        if len(self.normalized_host_ids) == 1:
            return "solo"
        return "dialogue"

    @property
    def hosts(self) -> Dict[str, str]:
        return {f"HOST_{i}": host_id for i, host_id in enumerate(self.normalized_host_ids, start=1)}


class PromptManager:
    """Responsible for building prompts based on user preferences"""

    _ROLE_PROMPT_MAP: Dict[str, Dict[str, str]] = {
        "architect": {
            "dialogue": "architect/architect-duo-long.md",
            "solo": "architect/architect_5min_solo.md",
        },
        "outliner": {
            "dialogue": "outliner/outline-duo-long.md",
            "solo": "outliner/outline-solo-short.md",
        },
        "scriptwriter": {
            "dialogue": "scriptwriter/scriptwriter-duo-long.md",
            "solo": "scriptwriter/scriptwriter_5min_solo.md",
        },
    }
    
    def __init__(self, podcast_config: PodcastConfig):
        self.podcast_config = podcast_config
        self.user_topic = podcast_config.topic
        self.host_ids = podcast_config.normalized_host_ids
        self.prompts_dir = PROMPTS_DIR

    @property
    def format(self) -> str:
        return self.podcast_config.effective_format

    
    def get_architect_prompt(self) -> str:
        """Build architect prompt"""
        prompt = self._load_role_prompt("architect")
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
        prompt = self._load_role_prompt("outliner")
        prompt = prompt.replace("{{BLUEPRINT}}", json.dumps(blueprint))
        prompt = prompt.replace("{{RESEARCH}}", json.dumps(research))
        prompt = prompt.replace("{{TOPIC}}", topic)
        
        return prompt
    
    def get_scriptwriter_prompt(self, outline: Dict, research: str, previous_scenes: str) -> str:
        """Build scriptwriter prompt with host information"""

        prompt = self._load_role_prompt("scriptwriter")
        
        # Inject host profiles
        hosts_info = format_hosts_for_prompt(self.host_ids)
        prompt = prompt.replace("{{HOSTS_PROFILES}}", hosts_info)
        
        prompt = prompt.replace("{{OUTLINE_JSON}}", json.dumps(outline))
        prompt = prompt.replace("{{RESEARCH_TEXT}}", research)
        prompt = prompt.replace("{{PREVIOUS_SCENES}}", previous_scenes)
        
        return prompt

    def _load_role_prompt(self, role: str) -> str:
        """Load a role prompt based on config format with dialogue fallback."""
        role_map = self._ROLE_PROMPT_MAP.get(role)
        if not role_map:
            raise ValueError(f"Unsupported prompt role: {role}")

        requested_format = self.format
        selected_rel_path = role_map.get(requested_format) or role_map.get("dialogue")
        if not selected_rel_path:
            raise FileNotFoundError(
                f"No prompt mapping found for role '{role}' and format '{requested_format}'"
            )

        selected_path = self.prompts_dir / selected_rel_path
        if selected_path.exists():
            return self._load_prompt_from_path(selected_path)

        dialogue_rel_path = role_map.get("dialogue")
        if dialogue_rel_path:
            dialogue_path = self.prompts_dir / dialogue_rel_path
            if dialogue_path.exists():
                return self._load_prompt_from_path(dialogue_path)

        raise FileNotFoundError(
            f"Prompt file not found for role '{role}' (requested format: '{requested_format}', "
            f"requested path: '{selected_rel_path}')"
        )
    
    def _load_base_prompt(self, filename: str) -> str:
        """Load base prompt file"""
        filepath = self.prompts_dir / filename
        return self._load_prompt_from_path(filepath)

    def _load_prompt_from_path(self, filepath: Path) -> str:
        """Load prompt file from a full path."""
        with open(filepath, 'r', encoding='utf-8') as f:
            return f.read()