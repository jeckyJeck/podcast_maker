"""
LLM Provider Interface and Base Types.

This module defines the abstract interface for LLM providers,
allowing swapping between different AI models (Gemini, OpenAI, etc.)
without changing core pipeline logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum


class OutputFormat(Enum):
    """Expected output format from the LLM."""
    JSON = "application/json"
    TEXT = "text/plain"


@dataclass
class LLMRequest:
    """Request configuration for LLM generation."""
    prompt: str
    model: str
    output_format: OutputFormat
    temperature: float = 0.7
    tools: list[Any] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


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
        model: str,
        temperature: float = 0.7,
        tools: Optional[list[Any]] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Generate plain text response.
        
        Args:
            prompt: The input prompt/instructions
            model: Model identifier (provider-specific)
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
        model: str,
        temperature: float = 0.7,
        metadata: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Generate and parse JSON response.
        
        Args:
            prompt: The input prompt/instructions
            model: Model identifier (provider-specific)
            temperature: Sampling temperature (0.0-1.0)
            metadata: Optional metadata for tracking/logging
            
        Returns:
            Parsed JSON as Python dict
            
        Raises:
            Exception: On critical failures or invalid JSON
            Returns dict with "error" key on non-critical parse failures
        """
        pass
