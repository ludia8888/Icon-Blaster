"""
Vector embedding service with caching, batching, and multiple provider support.
Integrates with TerminusDB for persistent storage of embeddings.
"""
from typing import List, Dict, Any, Optional, Union, Tuple
import asyncio
import json
import hashlib
import time
from datetime import datetime, timedelta
from dataclasses import asdict
import redis.asyncio as redis
# TerminusDB client will be injected via init
from .providers import (
    EmbeddingProviderFactory, EmbeddingConfig, EmbeddingProvider, BaseEmbeddingProvider,
    EmbeddingProviderError, EmbeddingAPIError, EmbeddingBatchSizeError, EmbeddingTokenLimitError
)
# Validation models not needed in microservice
# Circuit breaker will be handled at gateway level
from prometheus_client import Counter, Histogram, Gauge
import logging

logger = logging.getLogger(__name__)

# Metrics
embedding_requests_total = Counter("embedding_requests_total", "Total embedding requests", ["provider", "status"])
embedding_request_duration = Histogram("embedding_request_duration_seconds", "Embedding request duration", ["provider"])
embedding_cache_hits = Counter("embedding_cache_hits_total", "Embedding cache hits", ["provider"])
embedding_cache_misses = Counter("embedding_cache_misses_total", "Embedding cache misses", ["provider"])
embedding_batch_size = Histogram("embedding_batch_size", "Embedding batch sizes", ["provider"])
active_embedding_providers = Gauge("active_embedding_providers", "Number of active embedding providers")


class VectorEmbeddingService:
    """
    Enhanced vector embedding service supporting multiple providers and advanced features.
    """
    
    def __init__(self, 
                 terminus_client: TerminusDBClient,
                 redis_client: Optional[redis.Redis] = None,
                 cache_ttl: int = 3600):
        self.terminus_client = terminus_client
        self.redis_client = redis_client
        self.cache_ttl = cache_ttl
        self.providers: Dict[str, BaseEmbeddingProvider] = {}
        self.default_provider = None
        self.fallback_chain: List[str] = []  # Ordered list of providers for fallback
        
    async def register_provider(self, name: str, config: EmbeddingConfig, is_default: bool = False):
        """Register an embedding provider."""
        try:
            provider = EmbeddingProviderFactory.create_provider(config)
            self.providers[name] = provider
            
            if is_default or self.default_provider is None:
                self.default_provider = name
                
            # Store provider configuration in TerminusDB
            await self._store_provider_config(name, config)
            
            # Update metrics
            active_embedding_providers.set(len(self.providers))
            
            # Update fallback chain
            self._update_fallback_chain()
            
            logger.info(f"Registered embedding provider: {name}")
            
        except Exception as e:
            logger.error(f"Failed to register provider {name}: {e}")
            raise

    async def _store_provider_config(self, name: str, config: EmbeddingConfig):
        """Store provider configuration in TerminusDB."""
        config_doc = {
            "@type": "EmbeddingProviderConfig",
            "@id": f"provider_config_{name}",
            "name": name,
            "provider": config.provider.value,
            "model_name": config.model_name,
            "dimensions": config.dimensions,
            "max_tokens": config.max_tokens,
            "batch_size": config.batch_size,
            "timeout": config.timeout,
            "created_at": datetime.utcnow().isoformat(),
            "api_base": config.api_base
        }
        
        await self.terminus_client.insert_document(config_doc)

    @circuit_breaker("embedding_service")
    async def create_embeddings(self, 
                              texts: List[str],
                              provider_name: Optional[str] = None,
                              metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Create embeddings for multiple texts with caching and metadata.
        
        Returns:
            List of embedding objects with metadata
        """
        start_time = time.time()
        provider_name = provider_name or self.default_provider
        
        if not provider_name or provider_name not in self.providers:
            embedding_requests_total.labels(provider=provider_name or "unknown", status="error").inc()
            raise ValueError(f"Provider {provider_name} not found")
            
        provider = self.providers[provider_name]
        results = []
        
        # Record batch size
        embedding_batch_size.labels(provider=provider_name).observe(len(texts))
        
        # Check cache first
        cached_embeddings = await self._get_cached_embeddings(texts, provider_name)
        texts_to_compute = []
        cache_map = {}
        
        for i, text in enumerate(texts):
            cache_key = self._generate_cache_key(text, provider_name)
            if cache_key in cached_embeddings:
                embedding_cache_hits.labels(provider=provider_name).inc()
                results.append(cached_embeddings[cache_key])
            else:
                embedding_cache_misses.labels(provider=provider_name).inc()
                texts_to_compute.append(text)
                cache_map[len(texts_to_compute) - 1] = i
        
        # Compute missing embeddings
        if texts_to_compute:
            try:
                # Try with primary provider first, then fallback if needed
                new_embeddings = await self._create_embeddings_with_fallback(
                    texts_to_compute, provider_name
                )
                
                # Process and cache new embeddings
                for compute_idx, embedding in enumerate(new_embeddings):
                    original_idx = cache_map[compute_idx]
                    text = texts[original_idx]
                    
                    embedding_doc = {
                        "@type": "VectorEmbedding",
                        "@id": f"embedding_{hashlib.md5(text.encode()).hexdigest()}",
                        "text": text,
                        "embedding": embedding,
                        "provider": provider_name,
                        "model": provider.config.model_name,
                        "dimensions": len(embedding),
                        "created_at": datetime.utcnow().isoformat(),
                        "metadata": metadata or {}
                    }
                    
                    # Store in TerminusDB
                    await self.terminus_client.insert_document(embedding_doc)
                    
                    # Cache for future use
                    await self._cache_embedding(text, provider_name, embedding_doc)
                    
                    # Insert at correct position
                    if original_idx < len(results):
                        results.insert(original_idx, embedding_doc)
                    else:
                        results.append(embedding_doc)
                
                # Record success metrics
                embedding_requests_total.labels(provider=provider_name, status="success").inc()
                        
            except EmbeddingTokenLimitError as e:
                # Record specific error metrics
                embedding_requests_total.labels(provider=provider_name, status="token_limit_error").inc()
                logger.error(f"Token limit exceeded with provider {provider_name}: {e}")
                # Could implement automatic text truncation here
                raise
            except EmbeddingAPIError as e:
                # Record API error metrics
                embedding_requests_total.labels(provider=provider_name, status="api_error").inc()
                logger.error(f"API error with provider {provider_name}: {e}")
                # Could implement fallback to another provider here
                raise
            except EmbeddingProviderError as e:
                # Record provider error metrics
                embedding_requests_total.labels(provider=provider_name, status="provider_error").inc()
                logger.error(f"Provider error with {provider_name}: {e}")
                raise
            except Exception as e:
                # Record unknown error metrics
                embedding_requests_total.labels(provider=provider_name, status="unknown_error").inc()
                logger.error(f"Unexpected error with provider {provider_name}: {e}")
                raise
        
        # Record duration
        duration = time.time() - start_time
        embedding_request_duration.labels(provider=provider_name).observe(duration)
                
        return results

    async def semantic_search(self,
                            query: str,
                            collection_filter: Optional[Dict[str, Any]] = None,
                            top_k: int = 10,
                            similarity_threshold: float = 0.7,
                            provider_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Perform semantic search using vector embeddings.
        """
        provider_name = provider_name or self.default_provider
        provider = self.providers[provider_name]
        
        # Create query embedding
        query_embedding = await provider.create_single_embedding(query)
        
        # Build WOQL query for document retrieval
        woql_query = self._build_semantic_search_query(
            query_embedding, collection_filter, top_k, similarity_threshold
        )
        
        # Execute search in TerminusDB
        results = await self.terminus_client.query(woql_query)
        
        # Calculate similarities and rank results
        ranked_results = []
        for result in results:
            if "embedding" in result:
                similarity = await self._calculate_cosine_similarity(
                    query_embedding, result["embedding"]
                )
                if similarity >= similarity_threshold:
                    result["similarity_score"] = similarity
                    ranked_results.append(result)
        
        # Sort by similarity score
        ranked_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        
        return ranked_results[:top_k]

    async def batch_similarity_search(self,
                                    queries: List[str],
                                    documents: List[str],
                                    provider_name: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        Perform batch similarity search for multiple queries against multiple documents.
        """
        provider_name = provider_name or self.default_provider
        provider = self.providers[provider_name]
        
        # Create embeddings for all queries and documents
        query_embeddings = await provider.create_embeddings(queries)
        doc_embeddings = await provider.create_embeddings(documents)
        
        results = {}
        
        for i, query in enumerate(queries):
            query_embedding = query_embeddings[i]
            similarities = await provider.similarity_search(
                query_embedding, doc_embeddings, top_k=len(documents)
            )
            
            # Add document text to results
            query_results = []
            for sim_result in similarities:
                doc_idx = sim_result["index"]
                query_results.append({
                    "document": documents[doc_idx],
                    "similarity": sim_result["similarity"],
                    "document_index": doc_idx
                })
            
            results[query] = query_results
            
        return results

    async def cluster_embeddings(self,
                               embedding_ids: List[str],
                               n_clusters: int = 5,
                               algorithm: str = "kmeans") -> Dict[str, Any]:
        """
        Cluster embeddings using various clustering algorithms.
        """
        from sklearn.cluster import KMeans, DBSCAN, AgglomerativeClustering
        import numpy as np
        
        # Retrieve embeddings from TerminusDB
        embeddings_data = []
        for embedding_id in embedding_ids:
            doc = await self.terminus_client.get_document(embedding_id)
            if doc and "embedding" in doc:
                embeddings_data.append({
                    "id": embedding_id,
                    "embedding": doc["embedding"],
                    "text": doc.get("text", ""),
                    "metadata": doc.get("metadata", {})
                })
        
        if not embeddings_data:
            return {"clusters": [], "algorithm": algorithm, "n_clusters": 0}
        
        # Extract embeddings matrix
        embeddings_matrix = np.array([item["embedding"] for item in embeddings_data])
        
        # Apply clustering algorithm
        if algorithm == "kmeans":
            clusterer = KMeans(n_clusters=n_clusters, random_state=42)
        elif algorithm == "dbscan":
            clusterer = DBSCAN(eps=0.5, min_samples=2)
        elif algorithm == "hierarchical":
            clusterer = AgglomerativeClustering(n_clusters=n_clusters)
        else:
            raise ValueError(f"Unsupported clustering algorithm: {algorithm}")
        
        cluster_labels = clusterer.fit_predict(embeddings_matrix)
        
        # Group results by cluster
        clusters = {}
        for i, label in enumerate(cluster_labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(embeddings_data[i])
        
        # Store clustering results in TerminusDB
        clustering_result = {
            "@type": "ClusteringResult",
            "@id": f"clustering_{datetime.utcnow().isoformat()}",
            "algorithm": algorithm,
            "n_clusters": len(clusters),
            "embedding_ids": embedding_ids,
            "clusters": {str(k): v for k, v in clusters.items()},
            "created_at": datetime.utcnow().isoformat()
        }
        
        await self.terminus_client.insert_document(clustering_result)
        
        return clustering_result

    def _build_semantic_search_query(self,
                                   query_embedding: List[float],
                                   collection_filter: Optional[Dict[str, Any]],
                                   top_k: int,
                                   similarity_threshold: float) -> Dict[str, Any]:
        """Build WOQL query for semantic search."""
        # This is a simplified example - in practice, you'd use TerminusDB's vector search capabilities
        woql_query = {
            "query": {
                "@type": "Triple",
                "subject": {"@type": "Variable", "name": "Doc"},
                "predicate": {"@type": "NodeValue", "node": "embedding"},
                "object": {"@type": "Variable", "name": "Embedding"}
            },
            "filter": collection_filter or {},
            "limit": top_k * 2  # Get more results for similarity filtering
        }
        
        return woql_query

    async def _calculate_cosine_similarity(self, 
                                         embedding1: List[float], 
                                         embedding2: List[float]) -> float:
        """Calculate cosine similarity between two embeddings."""
        import numpy as np
        
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
            
        return float(dot_product / (norm1 * norm2))

    async def _get_cached_embeddings(self, 
                                   texts: List[str], 
                                   provider_name: str) -> Dict[str, Dict[str, Any]]:
        """Get cached embeddings from Redis."""
        if not self.redis_client:
            return {}
            
        cache_keys = [self._generate_cache_key(text, provider_name) for text in texts]
        cached_values = await self.redis_client.mget(cache_keys)
        
        cached_embeddings = {}
        for i, cached_value in enumerate(cached_values):
            if cached_value:
                try:
                    cached_embeddings[cache_keys[i]] = json.loads(cached_value)
                except json.JSONDecodeError:
                    continue
                    
        return cached_embeddings

    async def _cache_embedding(self, 
                             text: str, 
                             provider_name: str, 
                             embedding_doc: Dict[str, Any]):
        """Cache embedding in Redis."""
        if not self.redis_client:
            return
            
        cache_key = self._generate_cache_key(text, provider_name)
        cache_value = json.dumps(embedding_doc)
        
        await self.redis_client.setex(cache_key, self.cache_ttl, cache_value)

    def _generate_cache_key(self, text: str, provider_name: str) -> str:
        """Generate cache key for text and provider combination."""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        return f"embedding:{provider_name}:{text_hash}"

    async def get_provider_stats(self) -> Dict[str, Any]:
        """Get statistics about embedding providers and usage."""
        stats = {
            "providers": {},
            "total_embeddings": 0,
            "cache_stats": {}
        }
        
        for name, provider in self.providers.items():
            # Query TerminusDB for embedding count by provider
            woql_query = {
                "query": {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "name": "Doc"},
                    "predicate": {"@type": "NodeValue", "node": "provider"},
                    "object": {"@type": "NodeValue", "node": name}
                }
            }
            
            results = await self.terminus_client.query(woql_query)
            
            stats["providers"][name] = {
                "model": provider.config.model_name,
                "dimensions": provider.config.dimensions,
                "embedding_count": len(results),
                "is_default": name == self.default_provider
            }
            
            stats["total_embeddings"] += len(results)
        
        # Get cache statistics if Redis is available
        if self.redis_client:
            try:
                info = await self.redis_client.info()
                stats["cache_stats"] = {
                    "used_memory": info.get("used_memory_human", "N/A"),
                    "connected_clients": info.get("connected_clients", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0)
                }
            except Exception as e:
                stats["cache_stats"] = {"error": str(e)}
        
        return stats
    
    def _update_fallback_chain(self):
        """Update the fallback chain based on available providers."""
        # Priority order for fallback
        priority_order = [
            ("openai", 1),
            ("azure_openai", 2),
            ("cohere", 3),
            ("huggingface", 4),
            ("local", 5),
            ("google_vertex", 6),
            ("anthropic", 7)
        ]
        
        # Sort available providers by priority
        available_providers = []
        for name, priority in priority_order:
            if name in self.providers:
                available_providers.append((priority, name))
        
        # Sort by priority and extract names
        available_providers.sort(key=lambda x: x[0])
        self.fallback_chain = [name for _, name in available_providers]
        
        logger.info(f"Updated fallback chain: {self.fallback_chain}")
    
    async def _create_embeddings_with_fallback(
        self, 
        texts: List[str], 
        preferred_provider: str
    ) -> List[List[float]]:
        """Create embeddings with automatic fallback to other providers."""
        # Build provider chain starting with preferred
        provider_chain = []
        if preferred_provider in self.providers:
            provider_chain.append(preferred_provider)
        
        # Add other providers from fallback chain
        for provider_name in self.fallback_chain:
            if provider_name != preferred_provider:
                provider_chain.append(provider_name)
        
        last_error = None
        attempted_providers = []
        
        # Try each provider in order
        for provider_name in provider_chain:
            provider = self.providers.get(provider_name)
            if not provider:
                continue
                
            attempted_providers.append(provider_name)
            
            try:
                logger.info(f"Attempting to create embeddings with provider: {provider_name}")
                embeddings = await provider.create_embeddings_with_batching(texts)
                
                # Success - record which provider was used
                if provider_name != preferred_provider:
                    logger.warning(
                        f"Fallback successful: {preferred_provider} → {provider_name}"
                    )
                    embedding_requests_total.labels(
                        provider=f"{preferred_provider}_fallback_{provider_name}", 
                        status="success"
                    ).inc()
                
                return embeddings
                
            except EmbeddingAPIError as e:
                last_error = e
                logger.warning(f"Provider {provider_name} failed with API error: {e}")
                continue
                
            except Exception as e:
                last_error = e
                logger.error(f"Provider {provider_name} failed with unexpected error: {e}")
                continue
        
        # All providers failed
        error_msg = (
            f"All providers failed. Attempted: {attempted_providers}. "
            f"Last error: {last_error}"
        )
        logger.error(error_msg)
        raise EmbeddingProviderError(error_msg)