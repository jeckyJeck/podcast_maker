"""
Gemini LLM Provider Implementation.

Wraps Google's Gemini API (google.genai) and provides a unified
interface for text and JSON generation.
"""

import json
import os
from typing import Optional, Any
from google import genai
from google.genai import types

from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.rate_limiter import RateLimiter
from podcast_maker.services.llm_provider import (
    LLMProvider,
    LLMResponse,
    OutputFormat
)

logger = get_logger()


class GeminiAdapter(LLMProvider):
    """
    Gemini implementation of LLM provider.
    
    Handles:
    - Direct integration with google.genai.Client
    - Response parsing and validation
    - Usage tracking and logging
    - Rate limiting for API calls
    - Hybrid error policy (fail-fast for critical, fallback for non-critical)
    """
    
    _instance: Optional["GeminiAdapter"] = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """
        Initialize Gemini adapter.
        """
        if self.__class__._initialized:
            return

        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is missing. Set it in backend/.env")

        self.client = genai.Client(api_key=api_key)
        self.rate_limiter = RateLimiter(max_requests=20, period_seconds=86400)
        self.__class__._initialized = True
        
    def generate_text(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        tools: Optional[list[Any]] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Generate plain text response using Gemini.
        
        Args:
            prompt: The input prompt/instructions
            model: Gemini model name (e.g., "gemini-2.5-flash")
            temperature: Sampling temperature (0.0-1.0)
            tools: Optional Gemini tools (e.g., types.Tool(google_search=...))
            metadata: Optional metadata for tracking/logging
            
        Returns:
            LLMResponse with text content and usage metrics
            
        Raises:
            Exception: On API errors or empty responses
        """
        metadata = metadata or {}
        stage = metadata.get("stage", "unknown")
        
        logger.info(
            "GeminiAdapter.generate_text called: stage=%s, model=%s, temperature=%s",
            stage, model, temperature
        )
        
        config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            temperature=temperature
        )
        
        if tools:
            config.tools = tools
        
        # Fixed limiter policy: 20 Gemini requests per day per process.
        self.rate_limiter.acquire()
        
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            
            if not response.text:
                error_msg = f"Gemini returned empty response for stage '{stage}'"
                logger.error(error_msg)
                raise ValueError(error_msg)
            
            # Extract usage metadata
            usage = response.usage_metadata
            llm_response = LLMResponse(
                text=response.text,
                prompt_tokens=usage.prompt_token_count if usage and usage.prompt_token_count else 0,
                response_tokens=usage.candidates_token_count if usage and usage.candidates_token_count else 0,
                total_tokens=usage.total_token_count if usage and usage.total_token_count else 0,
                metadata=metadata
            )
            
            logger.info(
                "GeminiAdapter.generate_text success: stage=%s, prompt_tokens=%d, response_tokens=%d, total_tokens=%d",
                stage, llm_response.prompt_tokens, llm_response.response_tokens, llm_response.total_tokens
            )
            
            return llm_response
            
        except Exception as e:
            logger.error("GeminiAdapter.generate_text failed: stage=%s, error=%s", stage, str(e))
            raise
    
    def generate_json(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        metadata: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Generate and parse JSON response using Gemini.
        
        Args:
            prompt: The input prompt/instructions
            model: Gemini model name (e.g., "gemini-2.5-flash")
            temperature: Sampling temperature (0.0-1.0)
            metadata: Optional metadata for tracking/logging
            
        Returns:
            Parsed JSON as Python dict
            
        Raises:
            Exception: On API errors
            Returns dict with "error" key on JSON parse failures (hybrid policy)
        """
        metadata = metadata or {}
        stage = metadata.get("stage", "unknown")
        
        logger.info(
            "GeminiAdapter.generate_json called: stage=%s, model=%s, temperature=%s",
            stage, model, temperature
        )
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=temperature
        )
        
        # Fixed limiter policy: 20 Gemini requests per day per process.
        self.rate_limiter.acquire()
        
        try:
            response = self.client.models.generate_content(
                model=model,
                contents=prompt,
                config=config
            )
            
            if not response.text:
                error_msg = f"Gemini returned empty response for stage '{stage}'"
                logger.error(error_msg)
                # Hybrid policy: return error dict for JSON parsing issues
                return {"error": "No content returned", "stage": stage}
            
            # Log usage
            usage = response.usage_metadata
            if usage:
                logger.info(
                    "GeminiAdapter.generate_json usage: stage=%s, prompt_tokens=%d, response_tokens=%d, total_tokens=%d",
                    stage,
                    usage.prompt_token_count if usage.prompt_token_count else 0,
                    usage.candidates_token_count if usage.candidates_token_count else 0,
                    usage.total_token_count if usage.total_token_count else 0
                )
            
            # Parse JSON
            try:
                json_data = json.loads(response.text)
                logger.info("GeminiAdapter.generate_json success: stage=%s", stage)
                return json_data
            except json.JSONDecodeError as parse_error:
                logger.error(
                    "GeminiAdapter.generate_json parse error: stage=%s, error=%s",
                    stage, str(parse_error)
                )
                # Hybrid policy: return error dict instead of raising
                return {
                    "error": "Invalid JSON",
                    "stage": stage,
                    "raw": response.text[:500]  # Truncate for logging
                }
                
        except Exception as e:
            logger.error("GeminiAdapter.generate_json failed: stage=%s, error=%s", stage, str(e))
            raise
