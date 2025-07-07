"""
Embedding Service Provider for dependency injection.
Uses embedding stub to support both local and microservice modes.
"""
from typing import Optional, Dict, Any
import os
from .base import Provider
from shared.embedding_stub import get_embedding_stub, EmbeddingStub
from common_logging.setup import get_logger

logger = get_logger(__name__)


class EmbeddingServiceProvider(Provider[EmbeddingStub]):
    """Provider for embedding service stub."""
    
    def __init__(self):
        super().__init__()
        self._stub = None
    
    async def provide(self) -> EmbeddingStub:
        """Provide embedding service stub instance."""
        if not self._stub:
            self._stub = get_embedding_stub()
            mode = "microservice" if os.getenv("USE_EMBEDDING_MS", "false").lower() == "true" else "local"
            logger.info(f"Embedding service provider initialized in {mode} mode")
        return self._stub
    
    async def initialize(self) -> None:
        """Initialize the provider."""
        # Stub is initialized on first use
        pass
    
    async def shutdown(self) -> None:
        """Clean up resources."""
        # Stub cleanup is handled internally
        logger.info("Embedding service provider shutdown complete")


# For backward compatibility
def get_embedding_service_provider() -> EmbeddingServiceProvider:
    """Get embedding service provider instance."""
    return EmbeddingServiceProvider()