"""
Vector Embeddings Module

This module provides comprehensive vector embedding capabilities supporting multiple AI providers:
- OpenAI (text-embedding-3-large)
- Cohere (embed-english-v3.0) 
- HuggingFace (via API and local models)
- Azure OpenAI
- Google Vertex AI
- Anthropic Claude (semantic analysis approach)
- Local Sentence Transformers

Features:
- Multi-provider support with automatic failover
- Redis caching for performance optimization
- Batch processing with automatic splitting
- TerminusDB integration for persistence
- Semantic search and clustering capabilities
- Circuit breaker and retry logic

Usage:
    # Using DI container (recommended)
    from bootstrap.providers import EmbeddingProviderFactory
    
    provider = await EmbeddingProviderFactory.create_production_provider(terminus_client)
    embedding_service = await provider.provide()
    
    # Direct usage
    from core.embeddings.service import VectorEmbeddingService
    from core.embeddings.providers import EmbeddingConfig, EmbeddingProvider
    
    service = VectorEmbeddingService(terminus_client, redis_client)
    await service.register_provider("openai", EmbeddingConfig(
        provider=EmbeddingProvider.OPENAI,
        model_name="text-embedding-3-large",
        api_key="your-key"
    ))
    
    embeddings = await service.create_embeddings(["Hello world", "Vector embeddings"])

Environment Variables:
    OPENAI_API_KEY: OpenAI API key
    COHERE_API_KEY: Cohere API key  
    AZURE_OPENAI_API_KEY: Azure OpenAI key
    AZURE_OPENAI_ENDPOINT: Azure OpenAI endpoint
    ANTHROPIC_API_KEY: Anthropic API key
    HUGGINGFACE_API_KEY: HuggingFace API key
    GOOGLE_CLOUD_PROJECT: Google Cloud project ID
"""

from .service import VectorEmbeddingService
from .providers import (
    EmbeddingProvider,
    EmbeddingConfig,
    EmbeddingProviderFactory as ProviderFactory,
    BaseEmbeddingProvider,
    OpenAIEmbeddingProvider,
    CohereEmbeddingProvider,
    HuggingFaceEmbeddingProvider,
    LocalSentenceTransformersProvider,
    AzureOpenAIEmbeddingProvider,
    GoogleVertexEmbeddingProvider,
    AnthropicEmbeddingProvider
)

__all__ = [
    # Service
    "VectorEmbeddingService",
    
    # Configuration
    "EmbeddingProvider",
    "EmbeddingConfig",
    
    # Factory
    "ProviderFactory",
    
    # Base classes
    "BaseEmbeddingProvider",
    
    # Concrete providers
    "OpenAIEmbeddingProvider",
    "CohereEmbeddingProvider", 
    "HuggingFaceEmbeddingProvider",
    "LocalSentenceTransformersProvider",
    "AzureOpenAIEmbeddingProvider",
    "GoogleVertexEmbeddingProvider",
    "AnthropicEmbeddingProvider"
]

# Version info
__version__ = "1.0.0"
__author__ = "OMS Platform Team"
__description__ = "Multi-provider vector embedding service with caching and persistence"