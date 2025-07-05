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


class LocalEmbeddingService:
    """Local embedding service using sentence transformers."""
    
    def __init__(self):
        self.model = None
    
    async def initialize(self):
        """Initialize the local model."""
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
    
    async def generate_embedding(self, text: str, metadata=None):
        """Generate embedding for text."""
        embedding = self.model.encode(text)
        return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
    
    async def generate_batch_embeddings(self, texts: List[str], metadata=None):
        """Generate embeddings for multiple texts."""
        embeddings = self.model.encode(texts)
        return [emb.tolist() if hasattr(emb, 'tolist') else list(emb) for emb in embeddings]
    
    async def calculate_similarity(self, embedding1, embedding2, metric="cosine"):
        """Calculate similarity between embeddings."""
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity
        
        if isinstance(embedding1, list):
            embedding1 = np.array(embedding1)
        if isinstance(embedding2, list):
            embedding2 = np.array(embedding2)
        
        if metric == "cosine":
            return float(cosine_similarity([embedding1], [embedding2])[0][0])
        else:
            return 0.0
    
    async def find_similar(self, query_embedding, collection="default", top_k=10, 
                          min_similarity=0.0, filters=None):
        """Find similar documents (basic implementation)."""
        return []  # Basic implementation


class DummyEmbeddingService:
    """Dummy embedding service for testing."""
    
    async def generate_embedding(self, text: str, metadata=None):
        """Generate dummy embedding."""
        import hashlib
        import numpy as np
        
        # Generate deterministic embedding based on text hash
        hash_obj = hashlib.md5(text.encode())
        seed = int(hash_obj.hexdigest()[:8], 16)
        np.random.seed(seed)
        return np.random.random(384).tolist()
    
    async def generate_batch_embeddings(self, texts: List[str], metadata=None):
        """Generate dummy embeddings for multiple texts."""
        return [await self.generate_embedding(text) for text in texts]
    
    async def calculate_similarity(self, embedding1, embedding2, metric="cosine"):
        """Calculate dummy similarity."""
        return 0.5  # Return fixed similarity
    
    async def find_similar(self, query_embedding, collection="default", top_k=10,
                          min_similarity=0.0, filters=None):
        """Find similar documents (dummy implementation)."""
        return []


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
            # Use basic sentence transformers for local mode
            try:
                from sentence_transformers import SentenceTransformer
                self._client = LocalEmbeddingService()
                await self._client.initialize()
            except ImportError:
                logger.warning("sentence-transformers not available, using dummy service")
                self._client = DummyEmbeddingService()
        
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