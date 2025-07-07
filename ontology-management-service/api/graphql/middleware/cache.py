"""
Lightweight Cache Middleware for GraphQL
Only loaded when ENABLE_GQL_CACHE=true
"""
import json
import hashlib
from typing import Dict, Any, Optional

import strawberry
from strawberry.types import Info

from common_logging.setup import get_logger

logger = get_logger(__name__)


class SimpleGraphQLCache:
    """Simple Redis-based GraphQL cache"""
    
    def __init__(self, redis_client, config):
        self.redis = redis_client
        self.config = config
        self.enabled = config.enable_cache and redis_client is not None
    
    def _generate_key(self, query: str, variables: Optional[Dict] = None) -> str:
        """Generate cache key from query and variables"""
        cache_input = f"{query}:{json.dumps(variables or {}, sort_keys=True)}"
        hash_key = hashlib.md5(cache_input.encode()).hexdigest()
        return f"{self.config.cache_key_prefix}{hash_key}"
    
    async def get(self, query: str, variables: Optional[Dict] = None) -> Optional[Any]:
        """Get cached result"""
        if not self.enabled:
            return None
            
        try:
            key = self._generate_key(query, variables)
            cached = await self.redis.get(key)
            if cached:
                logger.debug(f"Cache hit for key: {key}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Cache get error: {e}")
        
        return None
    
    async def set(self, query: str, variables: Optional[Dict], result: Any) -> None:
        """Cache result"""
        if not self.enabled:
            return
            
        try:
            key = self._generate_key(query, variables)
            await self.redis.setex(
                key, 
                self.config.cache_ttl,
                json.dumps(result)
            )
            logger.debug(f"Cached result for key: {key}")
        except Exception as e:
            logger.warning(f"Cache set error: {e}")


def create_cache_extension(redis_client, config):
    """Create cache extension for Strawberry"""
    if not config.enable_cache:
        return None
        
    cache = SimpleGraphQLCache(redis_client, config)
    
    class CacheExtension(strawberry.extensions.Extension):
        async def on_request_start(self):
            # Check cache before execution
            request = self.execution_context.context.get("request")
            if request and request.method == "GET":
                # Only cache GET requests (queries)
                query = self.execution_context.query
                variables = self.execution_context.variables
                
                cached_result = await cache.get(query, variables)
                if cached_result:
                    # Return cached result directly
                    self.execution_context.result = cached_result
                    return cached_result
        
        async def on_request_end(self):
            # Cache successful results
            if hasattr(self.execution_context, 'result') and not self.execution_context.errors:
                request = self.execution_context.context.get("request")
                if request and request.method == "GET":
                    query = self.execution_context.query
                    variables = self.execution_context.variables
                    await cache.set(query, variables, self.execution_context.result)
    
    return CacheExtension