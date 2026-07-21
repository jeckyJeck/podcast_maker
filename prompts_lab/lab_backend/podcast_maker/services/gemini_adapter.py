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
)

logger = get_logger()


# Rate limit quotas per Gemini model, as (requests_per_minute, requests_per_day).
# Google publishes/updates these per model+tier, so keep this table as the single
# place to tweak the numbers when quotas change.
GEMINI_MODEL_RATE_LIMITS: dict[str, tuple[int, int]] = {
    "gemini-2.5-pro": (5, 100),
    "gemini-2.5-flash": (10, 250),
    "gemini-2.5-flash-lite": (15, 1000),
    "gemini-2.0-flash": (15, 200),
    "gemini-2.0-flash-lite": (30, 200),
    "gemma-4-31b-it": (30, 14400),
}

# Used when self.model isn't a key in GEMINI_MODEL_RATE_LIMITS above.
DEFAULT_RATE_LIMIT_RPM = 15
DEFAULT_RATE_LIMIT_RPD = 200

# Order in which to try other models once the configured model's *daily* quota
# is exhausted. The configured model (GEMINI_MODEL) is always tried first;
# these are tried afterwards, in this order, skipping duplicates.
GEMINI_MODEL_FALLBACK_ORDER: list[str] = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash-lite",
    "gemma-4-31b-it",
]


class GeminiQuotaExceededError(Exception):
    """Raised when every candidate Gemini model has exhausted its daily quota."""


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
        self.model = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")

        # self.model is always the first candidate; fallback models are appended
        # (skipping duplicates) so a daily-quota switch has somewhere to go.
        self._candidate_models = [self.model] + [
            m for m in GEMINI_MODEL_FALLBACK_ORDER if m != self.model
        ]

        self._minute_rate_limiters: dict[str, RateLimiter] = {}
        self._day_rate_limiters: dict[str, RateLimiter] = {}
        for candidate in self._candidate_models:
            requests_per_minute, requests_per_day = GEMINI_MODEL_RATE_LIMITS.get(
                candidate, (DEFAULT_RATE_LIMIT_RPM, DEFAULT_RATE_LIMIT_RPD)
            )
            self._minute_rate_limiters[candidate] = RateLimiter(max_requests=requests_per_minute, period_seconds=60)
            self._day_rate_limiters[candidate] = RateLimiter(max_requests=requests_per_day, period_seconds=86400)

        self.__class__._initialized = True

    def _select_model_for_request(self) -> str:
        """
        Pick which model to use for the next API call, applying this policy:
        - Per-minute quota hit -> block and wait for the same model (short wait, <=60s).
        - Per-day quota hit -> log it and move on to the next fallback model.
        - Every candidate's daily quota exhausted -> raise GeminiQuotaExceededError.
        """
        previous_model = None

        for candidate in self._candidate_models:
            # Blocks (sleeps) here if we're only over the per-minute quota.
            self._minute_rate_limiters[candidate].acquire()

            if self._day_rate_limiters[candidate].try_acquire():
                if previous_model is not None:
                    logger.warning(
                        "GeminiAdapter: daily quota exhausted for model=%s, switching to fallback model=%s",
                        previous_model, candidate
                    )
                return candidate

            logger.warning("GeminiAdapter: daily quota exhausted for model=%s", candidate)
            previous_model = candidate

        raise GeminiQuotaExceededError(
            f"Daily Gemini quota exhausted for all candidate models: {self._candidate_models}"
        )
        
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
            GeminiQuotaExceededError: If every candidate model's daily quota is exhausted
            Exception: On API errors or empty responses
        """
        metadata = metadata or {}
        stage = metadata.get("stage", "unknown")

        config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            temperature=temperature
        )

        if tools:
            config.tools = tools

        # Per-model limiter policy: see GEMINI_MODEL_RATE_LIMITS / GEMINI_MODEL_FALLBACK_ORDER above.
        try:
            model_name = self._select_model_for_request()
        except GeminiQuotaExceededError as e:
            logger.error("GeminiAdapter.generate_text failed: stage=%s, error=%s", stage, str(e))
            raise

        logger.info(
            "GeminiAdapter.generate_text called: stage=%s, model=%s, temperature=%s",
            stage, model_name, temperature
        )

        try:
            response = self.client.models.generate_content(
                model=model_name,
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
            GeminiQuotaExceededError: If every candidate model's daily quota is exhausted
            Exception: On API errors
            Returns dict with "error" key on JSON parse failures (hybrid policy)
        """
        metadata = metadata or {}
        stage = metadata.get("stage", "unknown")

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=temperature
        )

        # Per-model limiter policy: see GEMINI_MODEL_RATE_LIMITS / GEMINI_MODEL_FALLBACK_ORDER above.
        try:
            model_name = self._select_model_for_request()
        except GeminiQuotaExceededError as e:
            logger.error("GeminiAdapter.generate_json failed: stage=%s, error=%s", stage, str(e))
            raise

        logger.info(
            "GeminiAdapter.generate_json called: stage=%s, model=%s, temperature=%s",
            stage, model_name, temperature
        )

        try:
            response = self.client.models.generate_content(
                model=model_name,
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
