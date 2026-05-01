from podcast_maker.services.gemini_adapter import GeminiAdapter
from podcast_maker.services.llm_provider import LLMProvider


def build_llm_provider(provider_name: str = "gemini") -> LLMProvider:
    """Build an LLM provider from a provider name."""
    normalized = (provider_name or "gemini").strip().lower()

    if normalized == "gemini":
        return GeminiAdapter()

    raise ValueError(
        f"Unsupported LLM provider '{provider_name}'. Supported providers: gemini"
    )
