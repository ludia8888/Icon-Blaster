"""
Embedding Service Provider for dependency injection.
Provides singleton vector embedding service with multiple providers and Redis caching.
"""
from typing import Optional, Dict, Any
import os
from .base import SingletonProvider
from ...core.embeddings.service import VectorEmbeddingService
from ...core.embeddings.providers import EmbeddingProviderFactory, EmbeddingConfig, EmbeddingProvider
from ...database.clients.terminus_db import TerminusDBClient
from ...config.redis_config import get_redis_client
from utils.logger import get_logger

logger = get_logger(__name__)


class EmbeddingServiceProvider(SingletonProvider[VectorEmbeddingService]):
    """Provider for vector embedding service with all dependencies."""
    
    def __init__(self, 
                 terminus_client: TerminusDBClient,
                 cache_ttl: int = 3600):
        super().__init__()
        self.terminus_client = terminus_client
        self.cache_ttl = cache_ttl
    
    async def _create(self) -> VectorEmbeddingService:
        """Create vector embedding service instance with Redis caching."""
        
        # Initialize Redis client
        redis_client = None
        try:
            redis_client = await get_redis_client()
            logger.info("Redis client initialized for embedding service")
        except Exception as e:
            logger.warning(f"Failed to initialize Redis client: {e}")
        
        # Create embedding service
        service = VectorEmbeddingService(
            terminus_client=self.terminus_client,
            redis_client=redis_client,
            cache_ttl=self.cache_ttl
        )
        
        # Register default providers based on environment variables
        await self._register_default_providers(service)
        
        logger.info("Vector embedding service created with all dependencies")
        return service
    
    async def _register_default_providers(self, service: VectorEmbeddingService):
        """Register embedding providers based on available API keys."""
        
        # OpenAI Provider
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            await self._register_provider_safe(
                service, 
                "openai", 
                EmbeddingConfig(
                    provider=EmbeddingProvider.OPENAI,
                    model_name="text-embedding-3-large",
                    api_key=openai_key,
                    dimensions=3072,
                    batch_size=100
                ),
                is_default=True
            )
        
        # Cohere Provider
        cohere_key = os.getenv("COHERE_API_KEY")
        if cohere_key:
            await self._register_provider_safe(
                service,
                "cohere",
                EmbeddingConfig(
                    provider=EmbeddingProvider.COHERE,
                    model_name="embed-english-v3.0",
                    api_key=cohere_key,
                    dimensions=1024,
                    batch_size=96
                ),
                is_default=not openai_key  # Default if no OpenAI
            )
        
        # Azure OpenAI Provider
        azure_key = os.getenv("AZURE_OPENAI_API_KEY")
        azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        if azure_key and azure_endpoint:
            await self._register_provider_safe(
                service,
                "azure_openai",
                EmbeddingConfig(
                    provider=EmbeddingProvider.AZURE_OPENAI,
                    model_name="text-embedding-3-large",
                    api_key=azure_key,
                    api_base=azure_endpoint,
                    dimensions=3072,
                    batch_size=100
                )
            )
        
        # Anthropic Provider
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        if anthropic_key:
            await self._register_provider_safe(
                service,
                "anthropic",
                EmbeddingConfig(
                    provider=EmbeddingProvider.ANTHROPIC_CLAUDE,
                    model_name="claude-3-haiku-20240307",
                    api_key=anthropic_key,
                    dimensions=384,
                    batch_size=20
                )
            )
        
        # Local Sentence Transformers (Always available)
        await self._register_provider_safe(
            service,
            "local",
            EmbeddingConfig(
                provider=EmbeddingProvider.LOCAL_SENTENCE_TRANSFORMERS,
                model_name="all-MiniLM-L6-v2",
                dimensions=384,
                batch_size=32
            ),
            is_default=not any([openai_key, cohere_key])  # Fallback default
        )
        
        # HuggingFace Provider
        hf_key = os.getenv("HUGGINGFACE_API_KEY")
        if hf_key:
            await self._register_provider_safe(
                service,
                "huggingface",
                EmbeddingConfig(
                    provider=EmbeddingProvider.HUGGINGFACE,
                    model_name="sentence-transformers/all-MiniLM-L6-v2",
                    api_key=hf_key,
                    dimensions=384,
                    batch_size=50
                )
            )
        
        # Google Vertex AI Provider
        google_project = os.getenv("GOOGLE_CLOUD_PROJECT")
        if google_project:
            await self._register_provider_safe(
                service,
                "google_vertex",
                EmbeddingConfig(
                    provider=EmbeddingProvider.GOOGLE_VERTEX,
                    model_name="textembedding-gecko@003",
                    dimensions=768,
                    batch_size=25
                )
            )
    
    async def _register_provider_safe(self, 
                                    service: VectorEmbeddingService, 
                                    name: str, 
                                    config: EmbeddingConfig,
                                    is_default: bool = False):
        """Safely register a provider with error handling."""
        try:
            await service.register_provider(name, config, is_default)
            logger.info(f"Registered embedding provider: {name}")
        except Exception as e:
            logger.warning(f"Failed to register provider {name}: {e}")
    
    async def shutdown(self) -> None:
        """Clean up embedding service resources."""
        if self._instance:
            # Close Redis connections and clean up providers
            if self._instance.redis_client:
                await self._instance.redis_client.close()
            logger.info("Embedding service provider shutdown complete")


class EmbeddingProviderFactory:
    """Factory for creating embedding service providers with proper configuration."""
    
    @staticmethod
    async def create_production_provider(
        terminus_client: TerminusDBClient,
        cache_ttl: int = 3600
    ) -> EmbeddingServiceProvider:
        """Create production embedding provider with full Redis integration."""
        
        provider = EmbeddingServiceProvider(
            terminus_client=terminus_client,
            cache_ttl=cache_ttl
        )
        
        logger.info("Production embedding service provider created")
        return provider
    
    @staticmethod
    def create_test_provider(
        terminus_client: TerminusDBClient,
        provider_configs: Optional[Dict[str, EmbeddingConfig]] = None
    ) -> EmbeddingServiceProvider:
        """Create test provider with custom configurations."""
        
        class TestEmbeddingServiceProvider(SingletonProvider[VectorEmbeddingService]):
            def __init__(self, terminus_client: TerminusDBClient, configs: Dict[str, EmbeddingConfig]):
                super().__init__()
                self.terminus_client = terminus_client
                self.configs = configs or {}
            
            async def _create(self) -> VectorEmbeddingService:
                service = VectorEmbeddingService(
                    terminus_client=self.terminus_client,
                    redis_client=None,  # No Redis in tests
                    cache_ttl=300
                )
                
                # Register test providers
                for name, config in self.configs.items():
                    try:
                        await service.register_provider(name, config, is_default=(name == "test"))
                    except Exception as e:
                        logger.warning(f"Failed to register test provider {name}: {e}")
                
                return service
            
            async def shutdown(self) -> None:
                pass
        
        return TestEmbeddingServiceProvider(terminus_client, provider_configs or {})