from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


DEFAULT_AGENT_PROVIDER = "ollama"
DEFAULT_OLLAMA_MODEL = "qwen3.5:9b"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
PROVIDERS = ["ollama", "gemini"]


@dataclass(frozen=True)
class ToolSpec:
    """Provider-neutral function tool definition."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """Provider-neutral function call returned by a model."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class AgentLLMResponse:
    """Raw model text plus an optional structured tool call."""

    text: str
    tool_call: ToolCall | None = None


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
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[ToolSpec] | None = None,
        stream_thoughts: bool = False,
    ) -> AgentLLMResponse:
        """Return the model response, including a structured tool call when available."""


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

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[ToolSpec] | None = None,
        stream_thoughts: bool = False,
    ) -> AgentLLMResponse:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        ollama_tools = [_ollama_tool(tool) for tool in tools or []]
        if not stream_thoughts:
            response = self._client.chat(
                model=self._model,
                messages=messages,
                tools=ollama_tools or None,
            )
            print("input tokens:", response.get("prompt_eval_count"), "output tokens:", response.get("eval_count"))
            message = response.get("message", {})
            tool_call = _first_ollama_tool_call(message.get("tool_calls") or [])
            return AgentLLMResponse(text=message.get("content", "") or "", tool_call=tool_call)

        chunks: list[str] = []
        if ollama_tools:
            print(
                "Ollama streaming does not expose tool calls reliably; using streamed text fallback.",
                file=sys.stderr,
                flush=True,
            )
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
        if not chunks:
            print("no response got")
        return AgentLLMResponse(text="".join(chunks))


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

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[ToolSpec] | None = None,
        stream_thoughts: bool = False,
    ) -> AgentLLMResponse:
        if stream_thoughts:
            print(
                f"{self.provider_name} provider does not support streamed thoughts; continuing normally.",
                file=sys.stderr,
                flush=True,
            )
        from google.genai import types

        gemini_tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(
                        name=tool.name,
                        description=tool.description,
                        parameters=tool.parameters,
                    )
                    for tool in tools or []
                ]
            )
        ] if tools else None
        config = types.GenerateContentConfig(system_instruction=system_prompt, tools=gemini_tools)
        response = self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=config,
        )
        return AgentLLMResponse(text=response.text or "", tool_call=_first_gemini_tool_call(response))


def _ollama_tool(tool: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _first_ollama_tool_call(tool_calls: list[Any]) -> ToolCall | None:
    if not tool_calls:
        return None
    call = tool_calls[0]
    function = call.get("function", {}) if isinstance(call, dict) else getattr(call, "function", {})
    name = function.get("name") if isinstance(function, dict) else getattr(function, "name", None)
    arguments = function.get("arguments", {}) if isinstance(function, dict) else getattr(function, "arguments", {})
    if not name:
        return None
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolCall(name=name, arguments=arguments)


def _first_gemini_tool_call(response: Any) -> ToolCall | None:
    function_calls = getattr(response, "function_calls", None) or []
    if function_calls:
        call = function_calls[0]
        args = getattr(call, "args", {}) or {}
        return ToolCall(name=getattr(call, "name", ""), arguments=dict(args))

    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            function_call = getattr(part, "function_call", None)
            if function_call:
                args = getattr(function_call, "args", {}) or {}
                return ToolCall(name=getattr(function_call, "name", ""), arguments=dict(args))
    return None


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
