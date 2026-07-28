from src.domain.interfaces.embedding_provider import EmbeddingProvider
from src.infrastructure.config.settings import Settings


class EmbeddingProviderFactory:
    """Factory that creates the appropriate embedding provider based on configuration."""

    @staticmethod
    def create(settings: Settings) -> EmbeddingProvider:
        """Create an embedding provider instance based on the configured provider.

        Args:
            settings: Application settings containing the embedding provider
                configuration.

        Returns:
            An instance of the configured :class:`EmbeddingProvider`.

        Raises:
            ValueError: If the configured provider is not supported.
        """
        provider = settings.EMBEDDING_PROVIDER.lower()

        if provider == "gemini":
            from src.infrastructure.embeddings.gemini_embeddings import GeminiEmbeddingProvider

            return GeminiEmbeddingProvider(
                api_key=settings.GEMINI_API_KEY,
                model=settings.GEMINI_EMBEDDING_MODEL,
            )
        elif provider == "openai":
            from src.infrastructure.embeddings.openai_embeddings import OpenAIEmbeddingProvider

            return OpenAIEmbeddingProvider(
                api_key=settings.OPENAI_API_KEY,
                model=settings.OPENAI_EMBEDDING_MODEL,
            )
        elif provider == "huggingface":
            from src.infrastructure.embeddings.huggingface_embeddings import (
                HuggingFaceEmbeddingProvider,
            )

            return HuggingFaceEmbeddingProvider(model_name=settings.HUGGINGFACE_MODEL)
        else:
            raise ValueError(f"Unsupported embedding provider: {provider}")
