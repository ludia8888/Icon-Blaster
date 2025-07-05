"""
Embedding Service Client - Supports both local and remote modes
"""
import os
import logging
from typing import List, Dict, Any, Optional, Union
import numpy as np

logger = logging.getLogger(__name__)

# Check if we should use the microservice
USE_EMBEDDING_MS = os.getenv("USE_EMBEDDING_MS", "false").lower() == "true"


class EmbeddingClient:
    """
    Unified client for embedding operations.
    Automatically uses local or remote service based on configuration.
    """
    
    def __init__(self, endpoint: Optional[str] = None):
        self.use_microservice = USE_EMBEDDING_MS
        self.endpoint = endpoint or os.getenv("EMBEDDING_SERVICE_ENDPOINT", "embedding-service:50055")
        self._client = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the appropriate client"""
        if self._initialized:
            return
        
        if self.use_microservice:
            logger.info("Using remote embedding microservice")
            from shared.embedding_stub import EmbeddingStub
            self._client = EmbeddingStub(self.endpoint)
            await self._client.initialize()
        else:
            logger.info("Using local embedding service")
            from core.embeddings.service import VectorEmbeddingService
            from core.embeddings.providers import EmbeddingServiceProvider
            provider = EmbeddingServiceProvider()
            await provider.initialize()
            self._client = await provider.provide()
        
        self._initialized = True
    
    async def generate_embedding(
        self, 
        text: str, 
        metadata: Optional[Dict[str, Any]] = None
    ) -> Union[List[float], np.ndarray]:
        """Generate embedding for text"""
        if not self._initialized:
            await self.initialize()
        
        if self.use_microservice:
            return await self._client.generate_embedding(text, metadata)
        else:
            return await self._client.generate_embedding(text, metadata)
    
    async def generate_batch_embeddings(
        self,
        texts: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Union[List[float], np.ndarray]]:
        """Generate embeddings for multiple texts"""
        if not self._initialized:
            await self.initialize()
        
        if self.use_microservice:
            return await self._client.generate_batch_embeddings(texts, metadata)
        else:
            return await self._client.generate_batch_embeddings(texts, metadata)
    
    async def calculate_similarity(
        self,
        embedding1: Union[List[float], np.ndarray],
        embedding2: Union[List[float], np.ndarray],
        metric: str = "cosine"
    ) -> float:
        """Calculate similarity between embeddings"""
        if not self._initialized:
            await self.initialize()
        
        return await self._client.calculate_similarity(embedding1, embedding2, metric)
    
    async def find_similar(
        self,
        query_embedding: Union[List[float], np.ndarray],
        collection: str = "default",
        top_k: int = 10,
        min_similarity: float = 0.0,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Find similar documents"""
        if not self._initialized:
            await self.initialize()
        
        return await self._client.find_similar(
            query_embedding, collection, top_k, min_similarity, filters
        )
    
    async def store_embedding(
        self,
        id: str,
        embedding: Union[List[float], np.ndarray],
        collection: str = "default",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Store embedding with metadata"""
        if not self._initialized:
            await self.initialize()
        
        if self.use_microservice:
            return await self._client.store_embedding(id, embedding, collection, metadata)
        else:
            # Local service might not have store method
            logger.warning("Store embedding not implemented in local service")
            return True
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        if not self._initialized:
            await self.initialize()
        
        if hasattr(self._client, 'get_stats'):
            return await self._client.get_stats()
        else:
            return {"status": "unknown"}
    
    async def close(self):
        """Close the client"""
        if self._client and hasattr(self._client, 'close'):
            await self._client.close()
        self._initialized = False


# Global singleton instance
_embedding_client: Optional[EmbeddingClient] = None


async def get_embedding_client() -> EmbeddingClient:
    """Get or create the singleton embedding client"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
        await _embedding_client.initialize()
    return _embedding_client