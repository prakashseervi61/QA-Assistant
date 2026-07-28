from src.domain.interfaces.llm_provider import LLMProvider
from src.infrastructure.config.settings import Settings


class LLMProviderFactory:
    """Factory that creates the appropriate LLM provider based on configuration."""

    @staticmethod
    def create(settings: Settings) -> LLMProvider:
        """Create an LLM provider instance based on the configured provider.

        Args:
            settings: Application settings containing the LLM provider configuration.

        Returns:
            An instance of the configured :class:`LLMProvider`.

        Raises:
            ValueError: If the configured provider is not supported.
        """
        provider = settings.LLM_PROVIDER.lower()

        if provider == "deepseek":
            from src.infrastructure.llm.deepseek_provider import DeepSeekProvider

            return DeepSeekProvider(
                api_key=settings.DEEPSEEK_API_KEY,
                model=settings.DEEPSEEK_MODEL,
                base_url=getattr(
                    settings, "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
                ),
            )
        elif provider == "gemini":
            from src.infrastructure.llm.gemini_provider import GeminiProvider

            return GeminiProvider(
                api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_MODEL,
            )
        elif provider == "openai":
            from src.infrastructure.llm.openai_provider import OpenAIProvider

            return OpenAIProvider(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_MODEL,
            )
        elif provider == "anthropic":
            from src.infrastructure.llm.anthropic_provider import AnthropicProvider

            return AnthropicProvider(
                api_key=settings.ANTHROPIC_API_KEY,
                model=settings.ANTHROPIC_MODEL,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
