from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod


DEFAULT_AGENT_PROVIDER = "ollama"
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
PROVIDERS = ["ollama", "gemini"]


class AgentLLM(ABC):
    """Abstract interface for the optimization agent reasoning model."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable provider name used in logs and CLI output."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Concrete model name used by the provider."""

    @abstractmethod
    def complete(self, system_prompt: str, user_prompt: str, stream_thoughts: bool = False) -> str:
        """Return the model's raw text response."""


class OllamaAgentLLM(AgentLLM):
    def __init__(self, model: str = DEFAULT_OLLAMA_MODEL) -> None:
        try:
            import ollama
        except ImportError as exc:  # pragma: no cover - handled at runtime
            raise RuntimeError(
                "ollama is not installed. Install optimization_agent/requirements.txt "
                "and ensure a local model is available."
            ) from exc
        self._client = ollama
        self._model = model

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_prompt: str, stream_thoughts: bool = False) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if not stream_thoughts:
            response = self._client.chat(
                model=self._model,
                messages=messages,
            )
            return response["message"]["content"]

        chunks: list[str] = []
        print("\n--- Ollama stream start ---", file=sys.stderr, flush=True)
        for chunk in self._client.chat(
            model=self._model,
            messages=messages,
            stream=True,
        ):
            content = chunk.get("message", {}).get("content", "")
            if not content:
                continue
            chunks.append(content)
            print(content, end="", file=sys.stderr, flush=True)
        print("\n--- Ollama stream end ---", file=sys.stderr, flush=True)
        return "".join(chunks)


class GeminiAgentLLM(AgentLLM):
    def __init__(self, model: str = DEFAULT_GEMINI_MODEL) -> None:
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - handled at runtime
            raise RuntimeError(
                "google-genai is not installed. Install optimization_agent/requirements.txt."
            ) from exc
        self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self._model = model

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, system_prompt: str, user_prompt: str, stream_thoughts: bool = False) -> str:
        if stream_thoughts:
            print(
                f"{self.provider_name} provider does not support streamed thoughts; continuing normally.",
                file=sys.stderr,
                flush=True,
            )
        response = self._client.models.generate_content(
            model=self._model,
            contents=f"{system_prompt}\n\n{user_prompt}",
        )
        return response.text or ""


def build_agent_llm(provider: str | None = None, model: str | None = None) -> AgentLLM:
    resolved_provider = (provider or os.getenv("AGENT_PROVIDER") or DEFAULT_AGENT_PROVIDER).lower()
    resolved_model = model or os.getenv("AGENT_MODEL")

    if resolved_provider == "ollama":
        return OllamaAgentLLM(resolved_model or DEFAULT_OLLAMA_MODEL)
    if resolved_provider == "gemini":
        return GeminiAgentLLM(resolved_model or DEFAULT_GEMINI_MODEL)

    raise ValueError(
        f"Unknown agent provider: {resolved_provider}. "
        "Supported providers: ollama, gemini."
    )
