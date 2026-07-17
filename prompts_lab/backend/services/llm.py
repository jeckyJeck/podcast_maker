"""
LLM Provider Interface and Base Types for Prompts Lab.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, List, Dict


@dataclass
class TokenUsage:
    """Token usage metrics for a single LLM request."""
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """Unified response containing generated text/JSON and usage statistics."""
    text: str
    json_data: Optional[Dict[str, Any]] = None
    usage: TokenUsage = field(default_factory=TokenUsage)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers in the prompts lab.
    Allows easy model swapping and handles token accumulation and multi-turn correction.
    """

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Generate a plain text response.
        """
        pass

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        temperature: float = 0.7,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Generate a JSON response and parse it.
        """
        pass

    @abstractmethod
    def generate_follow_up(
        self,
        history: List[Dict[str, Any]],
        follow_up_message: str,
        temperature: float = 0.7,
        response_mime_type: str = "text/plain",
        metadata: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Send a follow-up correction request.
        
        Args:
            history: List of past messages in the conversation, formatted as:
                     [{'role': 'user'|'model', 'text': str}]
            follow_up_message: The feedback/error description to send to the model.
            temperature: Sampling temperature.
            response_mime_type: "text/plain" or "application/json".
        """
        pass

    @abstractmethod
    def get_tokens(self) -> int:
        """
        Get the total number of tokens used in the session since this instance was initialized.
        """
        pass
