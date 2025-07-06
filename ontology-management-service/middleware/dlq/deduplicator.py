"""
Message deduplicator for DLQ
"""
import hashlib
import json
from typing import Dict, Any, Optional, Set
from datetime import datetime, timedelta
import logging

from .models import DLQMessage

logger = logging.getLogger(__name__)


class MessageDeduplicator:
    """Deduplicates messages in DLQ"""
    
    def __init__(self, window_seconds: int = 3600):
        self.window_seconds = window_seconds
        self.logger = logger
        
        # Cache for recent message hashes
        self._hash_cache: Dict[str, datetime] = {}
        self._cache_cleanup_interval = 300  # 5 minutes
        self._last_cleanup = datetime.utcnow()
    
    def generate_hash(
        self,
        content: Dict[str, Any],
        include_keys: Optional[Set[str]] = None,
        exclude_keys: Optional[Set[str]] = None
    ) -> str:
        """Generate hash for message content"""
        try:
            # Filter content based on keys
            filtered_content = self._filter_content(
                content,
                include_keys,
                exclude_keys
            )
            
            # Sort keys for consistent hashing
            sorted_content = self._sort_dict(filtered_content)
            
            # Generate hash
            content_str = json.dumps(sorted_content, sort_keys=True)
            return hashlib.sha256(content_str.encode()).hexdigest()
            
        except Exception as e:
            self.logger.error(f"Failed to generate hash: {e}")
            # Fallback to simple string representation
            return hashlib.sha256(str(content).encode()).hexdigest()
    
    def is_duplicate(
        self,
        message: DLQMessage,
        content_hash: Optional[str] = None
    ) -> bool:
        """Check if message is a duplicate"""
        # Clean cache periodically
        self._cleanup_cache()
        
        # Use provided hash or generate new one
        if not content_hash:
            content_hash = self.generate_hash(message.content)
        
        # Check if hash exists in cache
        if content_hash in self._hash_cache:
            last_seen = self._hash_cache[content_hash]
            window_start = datetime.utcnow() - timedelta(
                seconds=self.window_seconds
            )
            
            if last_seen > window_start:
                self.logger.info(
                    f"Duplicate message detected: {message.id}"
                )
                return True
        
        # Update cache
        self._hash_cache[content_hash] = datetime.utcnow()
        
        return False
    
    def _filter_content(
        self,
        content: Dict[str, Any],
        include_keys: Optional[Set[str]],
        exclude_keys: Optional[Set[str]]
    ) -> Dict[str, Any]:
        """Filter content based on include/exclude keys"""
        if include_keys:
            # Only include specified keys
            return {
                k: v for k, v in content.items() 
                if k in include_keys
            }
        elif exclude_keys:
            # Exclude specified keys
            return {
                k: v for k, v in content.items() 
                if k not in exclude_keys
            }
        else:
            # Return all content
            return content
    
    def _sort_dict(self, obj: Any) -> Any:
        """Recursively sort dictionary for consistent hashing"""
        if isinstance(obj, dict):
            return {
                k: self._sort_dict(v) 
                for k, v in sorted(obj.items())
            }
        elif isinstance(obj, list):
            # Sort lists if they contain comparable items
            try:
                if all(isinstance(item, (str, int, float)) for item in obj):
                    return sorted(obj)
                else:
                    return [self._sort_dict(item) for item in obj]
            except:
                return [self._sort_dict(item) for item in obj]
        else:
            return obj
    
    def _cleanup_cache(self):
        """Clean up old entries from cache"""
        now = datetime.utcnow()
        
        # Check if cleanup is needed
        if (now - self._last_cleanup).seconds < self._cache_cleanup_interval:
            return
        
        # Remove old entries
        window_start = now - timedelta(seconds=self.window_seconds)
        old_hashes = [
            h for h, timestamp in self._hash_cache.items()
            if timestamp < window_start
        ]
        
        for h in old_hashes:
            del self._hash_cache[h]
        
        if old_hashes:
            self.logger.debug(f"Cleaned up {len(old_hashes)} old hashes")
        
        self._last_cleanup = now
    
    def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics"""
        return {
            "cache_size": len(self._hash_cache),
            "window_seconds": self.window_seconds,
            "last_cleanup": self._last_cleanup.isoformat()
        }
    
    def clear_cache(self):
        """Clear the hash cache"""
        self._hash_cache.clear()
        self._last_cleanup = datetime.utcnow()