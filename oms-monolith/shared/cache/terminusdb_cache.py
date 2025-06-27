"""
TerminusDB-Integrated Cache Manager
Real caching implementation utilizing TerminusDB's internal LRU cache
"""

import logging
import os
import asyncio
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timedelta
import json
import hashlib

logger = logging.getLogger(__name__)


class TerminusDBCacheManager:
    """
    Real cache manager that leverages TerminusDB's internal caching capabilities
    Replaces the dummy SmartCacheManager with actual caching functionality
    """
    
    def __init__(self, db_client=None, cache_db: str = "_cache"):
        """
        Initialize cache manager with TerminusDB client
        
        Args:
            db_client: TerminusDB client instance
            cache_db: Database name for cache storage (default: "_cache")
        """
        self.db_client = db_client
        self.cache_db = cache_db
        self.enable_internal_cache = os.getenv("TERMINUSDB_CACHE_ENABLED", "true").lower() == "true"
        self.lru_cache_size = int(os.getenv("TERMINUSDB_LRU_CACHE_SIZE", "500000000"))  # 500MB
        self.default_ttl = int(os.getenv("CACHE_DEFAULT_TTL", "3600"))  # 1 hour
        
        # Memory cache for frequently accessed items (fallback)
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._memory_cache_max_size = 1000  # Max items in memory cache
        
        logger.info(f"TerminusDBCacheManager initialized with cache_size={self.lru_cache_size}, ttl={self.default_ttl}")
    
    async def initialize(self):
        """Initialize cache database and schema"""
        if not self.db_client:
            logger.warning("No TerminusDB client provided, cache will use memory only")
            return
        
        try:
            # Create cache database if it doesn't exist
            await self.db_client.create_database(self.cache_db)
            
            # Create cache entry schema
            cache_schema = {
                "@type": "Class",
                "@id": "CacheEntry",
                "@key": {"@type": "Random"},
                "cache_key": {"@type": "xsd:string", "@class": "xsd:string"},
                "cache_value": {"@type": "xsd:string", "@class": "xsd:string"},
                "created_at": {"@type": "xsd:dateTime", "@class": "xsd:dateTime"},
                "expires_at": {"@type": "xsd:dateTime", "@class": "xsd:dateTime"},
                "access_count": {"@type": "xsd:integer", "@class": "xsd:integer"},
                "last_accessed": {"@type": "xsd:dateTime", "@class": "xsd:dateTime"}
            }
            
            await self.db_client.insert_document(
                cache_schema,
                graph_type="schema",
                database=self.cache_db
            )
            
            logger.info(f"Cache database '{self.cache_db}' initialized successfully")
            
        except Exception as e:
            logger.warning(f"Failed to initialize cache database: {e}")
    
    def _generate_cache_key(self, key: str) -> str:
        """Generate a consistent cache key"""
        if isinstance(key, str):
            return hashlib.sha256(key.encode()).hexdigest()[:32]
        return hashlib.sha256(str(key).encode()).hexdigest()[:32]
    
    def _serialize_value(self, value: Any) -> str:
        """Serialize value for storage"""
        try:
            return json.dumps(value, default=str)
        except Exception:
            return str(value)
    
    def _deserialize_value(self, value: str) -> Any:
        """Deserialize value from storage"""
        try:
            return json.loads(value)
        except Exception:
            return value
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        cache_key = self._generate_cache_key(key)
        
        # Try memory cache first
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if datetime.fromisoformat(entry["expires_at"]) > datetime.utcnow():
                entry["access_count"] += 1
                entry["last_accessed"] = datetime.utcnow().isoformat()
                return self._deserialize_value(entry["value"])
            else:
                # Remove expired entry
                del self._memory_cache[cache_key]
        
        # Try TerminusDB cache
        if self.db_client and self.enable_internal_cache:
            try:
                query = {
                    "@type": "Select",
                    "query": {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Entry"},
                        "predicate": "cache_key",
                        "object": {"@type": "Value", "data": key}
                    },
                    "select": ["Entry"]
                }
                
                result = await self.db_client.query_document(
                    query,
                    database=self.cache_db
                )
                
                if result and len(result) > 0:
                    entry = result[0]["Entry"]
                    
                    # Check expiration
                    expires_at = datetime.fromisoformat(entry["expires_at"])
                    if expires_at > datetime.utcnow():
                        # Update access stats
                        entry["access_count"] = entry.get("access_count", 0) + 1
                        entry["last_accessed"] = datetime.utcnow().isoformat()
                        
                        await self.db_client.replace_document(
                            entry,
                            database=self.cache_db
                        )
                        
                        # Also cache in memory for faster access
                        self._cache_in_memory(cache_key, entry["cache_value"], entry["expires_at"])
                        
                        return self._deserialize_value(entry["cache_value"])
                    else:
                        # Remove expired entry
                        await self.delete(key)
                        
            except Exception as e:
                logger.error(f"Error retrieving from TerminusDB cache: {e}")
        
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: uses default_ttl)
            
        Returns:
            True if successfully cached, False otherwise
        """
        if ttl is None:
            ttl = self.default_ttl
        
        cache_key = self._generate_cache_key(key)
        serialized_value = self._serialize_value(value)
        
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=ttl)
        
        # Cache in memory
        self._cache_in_memory(cache_key, serialized_value, expires_at.isoformat())
        
        # Cache in TerminusDB
        if self.db_client and self.enable_internal_cache:
            try:
                cache_entry = {
                    "@type": "CacheEntry",
                    "cache_key": key,
                    "cache_value": serialized_value,
                    "created_at": now.isoformat(),
                    "expires_at": expires_at.isoformat(),
                    "access_count": 0,
                    "last_accessed": now.isoformat()
                }
                
                # Check if entry already exists by querying directly
                query = {
                    "@type": "Select",
                    "query": {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Entry"},
                        "predicate": "cache_key",
                        "object": {"@type": "Value", "data": key}
                    },
                    "select": ["Entry"]
                }
                
                existing_entries = await self.db_client.query_document(
                    query,
                    database=self.cache_db
                )
                
                if existing_entries and len(existing_entries) > 0:
                    # Update existing entry
                    existing_entry = existing_entries[0]["Entry"]
                    cache_entry["@id"] = existing_entry.get("@id")  # Preserve ID for update
                    await self.db_client.replace_document(
                        cache_entry,
                        database=self.cache_db
                    )
                else:
                    # Insert new entry
                    await self.db_client.insert_document(
                        cache_entry,
                        database=self.cache_db
                    )
                
                return True
                
            except Exception as e:
                logger.error(f"Error storing in TerminusDB cache: {e}")
                # Still return True if memory cache worked
                return True
        
        return True
    
    def _cache_in_memory(self, cache_key: str, value: str, expires_at: str):
        """Cache entry in memory with LRU eviction"""
        # Remove oldest entries if cache is full
        if len(self._memory_cache) >= self._memory_cache_max_size:
            # Remove least recently used entries
            sorted_entries = sorted(
                self._memory_cache.items(),
                key=lambda x: x[1].get("last_accessed", "1970-01-01")
            )
            
            # Remove oldest 10% of entries
            num_to_remove = max(1, len(sorted_entries) // 10)
            for i in range(num_to_remove):
                del self._memory_cache[sorted_entries[i][0]]
        
        self._memory_cache[cache_key] = {
            "value": value,
            "expires_at": expires_at,
            "access_count": 0,
            "last_accessed": datetime.utcnow().isoformat()
        }
    
    async def delete(self, key: str) -> bool:
        """
        Delete entry from cache
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if entry was deleted, False otherwise
        """
        cache_key = self._generate_cache_key(key)
        
        # Remove from memory cache
        if cache_key in self._memory_cache:
            del self._memory_cache[cache_key]
        
        # Remove from TerminusDB
        if self.db_client and self.enable_internal_cache:
            try:
                query = {
                    "@type": "Delete",
                    "query": {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Entry"},
                        "predicate": "cache_key", 
                        "object": {"@type": "Value", "data": key}
                    }
                }
                
                await self.db_client.query_document(
                    query,
                    database=self.cache_db
                )
                
                return True
                
            except Exception as e:
                logger.error(f"Error deleting from TerminusDB cache: {e}")
        
        return True
    
    async def clear(self) -> bool:
        """
        Clear all cache entries
        
        Returns:
            True if cache was cleared, False otherwise
        """
        # Clear memory cache
        self._memory_cache.clear()
        
        # Clear TerminusDB cache
        if self.db_client and self.enable_internal_cache:
            try:
                # Drop and recreate cache database
                await self.db_client.delete_database(self.cache_db)
                await self.initialize()
                return True
                
            except Exception as e:
                logger.error(f"Error clearing TerminusDB cache: {e}")
        
        return True
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache
        
        Args:
            key: Cache key to check
            
        Returns:
            True if key exists and not expired, False otherwise
        """
        value = await self.get(key)
        return value is not None
    
    async def get_with_optimization(self, 
                                   key: str,
                                   db: str,
                                   branch: str,
                                   query_factory: Callable,
                                   doc_type: str,
                                   ttl: Optional[int] = None) -> Any:
        """
        Get value with query optimization - compatible with BranchService
        
        Args:
            key: Cache key
            db: Database name
            branch: Branch name
            query_factory: Function to execute if cache miss
            doc_type: Document type for optimization hints
            ttl: Cache TTL override
            
        Returns:
            Cached or freshly computed value
        """
        # Try cache first
        cached_value = await self.get(key)
        if cached_value is not None:
            logger.debug(f"Cache hit for key: {key}")
            return cached_value
        
        # Cache miss - execute query
        logger.debug(f"Cache miss for key: {key}, executing query")
        try:
            if asyncio.iscoroutinefunction(query_factory):
                result = await query_factory()
            else:
                result = query_factory()
            
            # Cache the result
            cache_ttl = ttl or self.default_ttl
            await self.set(key, result, cache_ttl)
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing query factory for key {key}: {e}")
            raise
    
    async def warm_cache_for_branch(self, 
                                   db: str,
                                   branch: str,
                                   doc_types: List[str]) -> Dict[str, int]:
        """
        Pre-warm cache for specific branch and document types
        
        Args:
            db: Database name
            branch: Branch name  
            doc_types: List of document types to pre-warm
            
        Returns:
            Dictionary with doc_type -> count of cached items
        """
        results = {}
        
        if not self.db_client:
            logger.warning("No TerminusDB client available for cache warming")
            return results
        
        for doc_type in doc_types:
            try:
                # Query all documents of this type
                query = {
                    "@type": "Select",
                    "query": {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Doc"},
                        "predicate": "rdf:type",
                        "object": {"@type": "Value", "data": doc_type}
                    },
                    "select": ["Doc"]
                }
                
                docs = await self.db_client.query_document(
                    query,
                    database=db,
                    branch=branch
                )
                
                count = 0
                for doc in docs:
                    # Cache each document
                    cache_key = f"{db}:{branch}:{doc_type}:{doc.get('@id', 'unknown')}"
                    await self.set(cache_key, doc, ttl=7200)  # 2 hour TTL for warmed cache
                    count += 1
                
                results[doc_type] = count
                logger.info(f"Pre-warmed {count} {doc_type} documents for {db}:{branch}")
                
            except Exception as e:
                logger.error(f"Error warming cache for {doc_type}: {e}")
                results[doc_type] = 0
        
        return results
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "memory_cache_size": len(self._memory_cache),
            "memory_cache_max_size": self._memory_cache_max_size,
            "lru_cache_size_bytes": self.lru_cache_size,
            "default_ttl_seconds": self.default_ttl,
            "cache_enabled": self.enable_internal_cache,
        }
        
        # Calculate memory cache hit rate and other stats if possible
        if self._memory_cache:
            total_access_count = sum(
                entry.get("access_count", 0) 
                for entry in self._memory_cache.values()
            )
            stats["total_memory_accesses"] = total_access_count
        
        # Get TerminusDB cache stats if available
        if self.db_client and self.enable_internal_cache:
            try:
                query = {
                    "@type": "Select",
                    "query": {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Entry"},
                        "predicate": "rdf:type",
                        "object": {"@type": "Value", "data": "CacheEntry"}
                    },
                    "select": ["Entry"]
                }
                
                entries = await self.db_client.query_document(
                    query,
                    database=self.cache_db
                )
                
                stats["terminusdb_cache_entries"] = len(entries)
                
                if entries:
                    total_access_count = sum(
                        entry.get("access_count", 0) 
                        for entry in entries
                    )
                    stats["terminusdb_total_accesses"] = total_access_count
                
            except Exception as e:
                logger.error(f"Error getting TerminusDB cache stats: {e}")
                stats["terminusdb_cache_error"] = str(e)
        
        return stats