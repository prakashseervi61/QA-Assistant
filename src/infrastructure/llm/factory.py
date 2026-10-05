from src.domain.interfaces.llm_provider import LLMProvider
from src.infrastructure.config.settings import Settings


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Build the Gemini LLM provider.

    ponytail: this was a switch over four providers. Only Gemini is wired up
    and only Gemini is configured, so the switch is gone; re-add it when a
    second provider is genuinely in use rather than in theory. The import stays
    lazy so `google-genai` is not pulled in at module import time.
    """
    from src.infrastructure.llm.gemini_provider import GeminiProvider

    return GeminiProvider(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
    )