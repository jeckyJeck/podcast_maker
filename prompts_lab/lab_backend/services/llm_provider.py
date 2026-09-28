"""
LLM Provider Interface and Base Types.

This module defines the abstract interface for LLM providers,
allowing swapping between different AI models (Gemini, OpenAI, etc.)
without changing core pipeline logic.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from dataclasses import dataclass, field


class LLMResponseParseError(Exception):
    """
    Raised when an LLM provider's response cannot be parsed into the
    expected structured format (e.g. invalid/empty JSON from generate_json).

    Carries the raw response text so callers/retry policies can inspect
    or log it without needing to re-derive it from a swallowed error dict.
    """

    def __init__(self, message: str, raw_response: str = "", stage: str = "unknown"):
        self.raw_response = raw_response
        self.stage = stage
        super().__init__(f"{message} (stage={stage}): {raw_response[:500]!r}")


@dataclass
class LLMResponse:
    """Response from LLM generation."""
    text: str
    prompt_tokens: int = 0
    response_tokens: int = 0
    total_tokens: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    
    Implementations should handle:
    - API authentication and configuration
    - Request/response mapping to provider-specific formats
    - Error handling and retries
    - Usage tracking and logging
    """
    
    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        tools: Optional[list[Any]] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Generate plain text response.
        
        Args:
            prompt: The input prompt/instructions
            temperature: Sampling temperature (0.0-1.0)
            tools: Optional provider-specific tools (e.g., GoogleSearch)
            metadata: Optional metadata for tracking/logging
            
        Returns:
            LLMResponse with text content and usage metrics
            
        Raises:
            Exception: On critical failures (API errors, invalid config)
        """
        pass
    
    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        temperature: float = 0.7,
        metadata: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Generate and parse JSON response.
        
        Args:
            prompt: The input prompt/instructions
            temperature: Sampling temperature (0.0-1.0)
            metadata: Optional metadata for tracking/logging
            
        Returns:
            Parsed JSON as Python dict

        Raises:
            Exception: On critical failures (e.g. API errors)
            LLMResponseParseError: If the response is empty or is not valid JSON
        """
        pass
