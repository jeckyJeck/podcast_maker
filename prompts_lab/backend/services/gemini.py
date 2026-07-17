"""
Gemini adapter implementing LLMProvider with google-genai.
"""

import json
import os
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import types
from google.genai.errors import APIError

from services.llm import LLMProvider, LLMResponse, TokenUsage


class GeminiAdapter(LLMProvider):
    """
    Gemini implementation of LLM provider.
    Maintains a running session token count and supports follow-up chat correction.
    """

    def __init__(self, model: str = "gemini-2.5-flash", api_key: Optional[str] = None):
        """
        Initialize the Gemini Adapter.
        """
        self.model = model
        actual_api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not actual_api_key:
            raise ValueError("GOOGLE_API_KEY is missing. Set it in .env or environment")
        
        self.client = genai.Client(api_key=actual_api_key)
        self._total_tokens = 0

    def _update_tokens(self, response) -> TokenUsage:
        usage = getattr(response, "usage_metadata", None)
        if not usage:
            return TokenUsage()
        
        prompt_tokens = usage.prompt_token_count or 0
        response_tokens = usage.candidates_token_count or 0
        total_tokens = usage.total_token_count or 0
        
        self._total_tokens += total_tokens
        return TokenUsage(
            prompt_tokens=prompt_tokens,
            response_tokens=response_tokens,
            total_tokens=total_tokens
        )

    def generate_text(
        self,
        prompt: str,
        temperature: float = 0.7,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            temperature=temperature
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )
            usage = self._update_tokens(response)
            text = response.text or ""
            return LLMResponse(text=text, usage=usage)
        except Exception as e:
            # Re-raise with diagnostic context
            raise RuntimeError(f"Gemini generate_text failed: {e}") from e

    def generate_json(
        self,
        prompt: str,
        temperature: float = 0.7,
        metadata: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=temperature
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config
            )
            usage = self._update_tokens(response)
            text = response.text or ""
            
            # Clean text if wrapped in markdown fences, though response_mime_type="application/json" usually handles this
            cleaned_text = text.strip()
            if cleaned_text.startswith("```"):
                # strip code fence if LLM returned it
                lines = cleaned_text.splitlines()
                if lines[0].startswith("```json") or lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_text = "\n".join(lines).strip()
            
            try:
                json_data = json.loads(cleaned_text)
            except json.JSONDecodeError as jde:
                # Return partial parsing error inside response rather than crashing completely,
                # letting engine handle it or initiate follow-up.
                json_data = {"error": "Invalid JSON returned by LLM", "raw_response": text, "exception": str(jde)}
            
            return LLMResponse(text=text, json_data=json_data, usage=usage)
        except Exception as e:
            raise RuntimeError(f"Gemini generate_json failed: {e}") from e

    def _map_history_to_contents(self, history: List[Dict[str, Any]]) -> List[types.Content]:
        contents = []
        for msg in history:
            role = msg.get("role")
            text = msg.get("text")
            
            # Map role names
            gemini_role = "user"
            if role in ("model", "assistant"):
                gemini_role = "model"
            
            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[types.Part.from_text(text=text)]
                )
            )
        return contents

    def generate_follow_up(
        self,
        history: List[Dict[str, Any]],
        follow_up_message: str,
        temperature: float = 0.7,
        response_mime_type: str = "text/plain",
        metadata: Optional[Dict[str, Any]] = None
    ) -> LLMResponse:
        # Build contents from history and append the new user follow-up message
        contents = self._map_history_to_contents(history)
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=follow_up_message)]
            )
        )

        config = types.GenerateContentConfig(
            response_mime_type=response_mime_type,
            temperature=temperature
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config
            )
            usage = self._update_tokens(response)
            text = response.text or ""
            
            json_data = None
            if response_mime_type == "application/json":
                cleaned_text = text.strip()
                if cleaned_text.startswith("```"):
                    lines = cleaned_text.splitlines()
                    if lines[0].startswith("```json") or lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    cleaned_text = "\n".join(lines).strip()
                try:
                    json_data = json.loads(cleaned_text)
                except json.JSONDecodeError as jde:
                    json_data = {"error": "Invalid JSON returned by LLM in follow-up", "raw_response": text, "exception": str(jde)}

            return LLMResponse(text=text, json_data=json_data, usage=usage)
        except Exception as e:
            raise RuntimeError(f"Gemini generate_follow_up failed: {e}") from e

    def get_tokens(self) -> int:
        return self._total_tokens
