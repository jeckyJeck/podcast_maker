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
from google.genai.errors import APIError, ServerError

from podcast_maker.core.logging_config import get_logger
from podcast_maker.core.rate_limiter import RateLimiter
from podcast_maker.services.llm_provider import (
    LLMProvider,
    LLMResponse,
)
from podcast_maker.services.retry import retry_network_call

logger = get_logger()
FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemma-4-31b-it")


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
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.rate_limiter = RateLimiter(max_requests=20, period_seconds=86400)
        self.__class__._initialized = True
        
    def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        tools: Optional[list[Any]] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> LLMResponse:
        """
        Generate plain text response using Gemini.
        
        Args:
            prompt: The input prompt/instructions
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
            stage, self.model, temperature
        )
        
        config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            temperature=temperature
        )
        
        if tools:
            config.tools = tools
        
        try:
            response = retry_network_call(
                f"gemini.generate_text.{stage}",
                lambda: self._generate_content(contents=prompt, config=config),
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
        temperature: float = 0.7,
        metadata: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """
        Generate and parse JSON response using Gemini.
        
        Args:
            prompt: The input prompt/instructions
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
            stage, self.model, temperature
        )
        
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=temperature
        )
        
        try:
            response = retry_network_call(
                f"gemini.generate_json.{stage}",
                lambda: self._generate_content(contents=prompt, config=config),
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

    def _generate_content(self, *, contents: str, config: types.GenerateContentConfig):
        # Fixed limiter policy: 20 Gemini requests per day per process.
        self.rate_limiter.acquire()
        try:
            return self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
        except ServerError as e:
            # 503 Service Unavailable is handled here (5xx)
            if e.code == 503:
                print(f"Primary model is experiencing high demand (503). Switching to fallback...")
                return self._call_fallback(contents, config)
            raise e
            
        except APIError as e:
            # 429 Rate Limit is a 4xx error, so it falls under ClientError/APIError
            if e.code == 429:
                print(f"Primary model hit rate limits (429). Switching to fallback...")
                return self._call_fallback(contents, config)
            raise e

    def _call_fallback(self, contents: str, config: types.GenerateContentConfig):
        # Fallback policy: switch to a cheaper model on 429/503 errors
        return self.client.models.generate_content(
            model=fallback_model,
            contents=contents,
            config=config,
        )
    
