from __future__ import annotations

from pathlib import Path
from typing import Any

from podcast_maker.core.prompt_manager import PromptManager, PodcastConfig


class InstrumentedOverridePromptManager(PromptManager):
    """Prompt manager with per-stage overrides and prompt capture."""

    def __init__(
        self,
        podcast_config: PodcastConfig,
        overrides: dict[str, Path] | None = None,
    ) -> None:
        super().__init__(podcast_config)
        self.overrides = overrides or {}
        self.resolved_prompts: dict[str, str] = {}

    def get_architect_prompt(self) -> str:
        prompt = super().get_architect_prompt()
        self.resolved_prompts["architect"] = prompt
        return prompt

    def get_researcher_prompt(self, segment: dict[str, Any]) -> str:
        prompt = super().get_researcher_prompt(segment)
        self.resolved_prompts["researcher"] = prompt
        return prompt

    def get_outliner_prompt(self, blueprint: dict, research: str, topic: str) -> str:
        prompt = super().get_outliner_prompt(blueprint, research, topic)
        self.resolved_prompts["outliner"] = prompt
        return prompt

    def get_scriptwriter_prompt(self, outline: dict, research: str, previous_scenes: str) -> str:
        prompt = super().get_scriptwriter_prompt(outline, research, previous_scenes)
        self.resolved_prompts["scriptwriter"] = prompt
        return prompt

    def _load_role_prompt(self, role: str) -> str:
        override = self.overrides.get(role)
        if override:
            return self._load_prompt_from_path(override)
        return super()._load_role_prompt(role)

    def _load_base_prompt(self, filename: str) -> str:
        # researcher uses researcher.md as base prompt
        if filename == "researcher.md":
            override = self.overrides.get("researcher")
            if override:
                return self._load_prompt_from_path(override)
        return super()._load_base_prompt(filename)
