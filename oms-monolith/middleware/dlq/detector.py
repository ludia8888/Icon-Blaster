"""
Poison message detector for DLQ
"""
import hashlib
import json
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
import logging

from .models import DLQMessage

logger = logging.getLogger(__name__)


class PoisonMessageDetector:
    """Detects poison messages based on patterns and history"""
    
    def __init__(self):
        self.logger = logger
        
        # Pattern matchers for known poison messages
        self._poison_patterns: List[Dict[str, Any]] = [
            {
                "name": "invalid_json",
                "check": self._check_invalid_json
            },
            {
                "name": "oversized_payload",
                "check": self._check_oversized_payload,
                "max_size": 1024 * 1024  # 1MB
            },
            {
                "name": "malformed_structure",
                "check": self._check_malformed_structure
            },
            {
                "name": "cyclic_reference",
                "check": self._check_cyclic_reference
            },
            {
                "name": "repeated_failure_pattern",
                "check": self._check_repeated_failure_pattern
            }
        ]
        
        # Cache for tracking failure patterns
        self._failure_cache: Dict[str, List[datetime]] = {}
        self._pattern_cache: Dict[str, int] = {}
    
    async def is_poison(
        self,
        message: DLQMessage,
        error_pattern_threshold: int = 5
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a message is poison
        Returns (is_poison, reason)
        """
        # Check each pattern
        for pattern in self._poison_patterns:
            try:
                is_poison = await pattern["check"](
                    message,
                    pattern.get("max_size"),
                    error_pattern_threshold
                )
                
                if is_poison:
                    reason = f"Detected poison pattern: {pattern['name']}"
                    self.logger.warning(
                        f"Message {message.id} identified as poison: {reason}"
                    )
                    return True, reason
                    
            except Exception as e:
                self.logger.error(
                    f"Error checking pattern {pattern['name']}: {e}"
                )
        
        # Check error history patterns
        if self._has_consistent_error_pattern(message):
            return True, "Consistent error pattern detected"
        
        # Check retry threshold
        if message.retry_count >= error_pattern_threshold:
            return True, f"Exceeded retry threshold ({error_pattern_threshold})"
        
        return False, None
    
    async def _check_invalid_json(
        self,
        message: DLQMessage,
        *args
    ) -> bool:
        """Check if message content is invalid JSON"""
        try:
            # Try to serialize and deserialize
            json_str = json.dumps(message.content)
            json.loads(json_str)
            return False
        except (TypeError, ValueError, RecursionError):
            return True
    
    async def _check_oversized_payload(
        self,
        message: DLQMessage,
        max_size: int,
        *args
    ) -> bool:
        """Check if message payload is too large"""
        try:
            size = len(json.dumps(message.content))
            return size > max_size
        except:
            # If we can't serialize, it might be poison
            return True
    
    async def _check_malformed_structure(
        self,
        message: DLQMessage,
        *args
    ) -> bool:
        """Check for malformed message structure"""
        content = message.content
        
        # Check for common malformed patterns
        if not isinstance(content, dict):
            return True
        
        # Check for required fields (customize based on your schema)
        required_fields = message.metadata.get("required_fields", [])
        for field in required_fields:
            if field not in content:
                return True
        
        # Check for deep nesting
        if self._get_max_depth(content) > 10:
            return True
        
        return False
    
    async def _check_cyclic_reference(
        self,
        message: DLQMessage,
        *args
    ) -> bool:
        """Check for cyclic references in message"""
        try:
            seen: Set[int] = set()
            
            def has_cycle(obj: Any, path: Set[int]) -> bool:
                obj_id = id(obj)
                
                if obj_id in path:
                    return True
                
                if isinstance(obj, (dict, list)):
                    path.add(obj_id)
                    
                    if isinstance(obj, dict):
                        for value in obj.values():
                            if has_cycle(value, path.copy()):
                                return True
                    else:  # list
                        for item in obj:
                            if has_cycle(item, path.copy()):
                                return True
                
                return False
            
            return has_cycle(message.content, seen)
            
        except:
            return True
    
    async def _check_repeated_failure_pattern(
        self,
        message: DLQMessage,
        *args,
        threshold: int = 5
    ) -> bool:
        """Check for repeated failure patterns"""
        # Generate pattern hash from error
        pattern_hash = self._generate_error_pattern_hash(
            message.error_message
        )
        
        # Track pattern occurrences
        if pattern_hash not in self._pattern_cache:
            self._pattern_cache[pattern_hash] = 0
        
        self._pattern_cache[pattern_hash] += 1
        
        # Check if pattern exceeds threshold
        return self._pattern_cache[pattern_hash] >= threshold
    
    def _has_consistent_error_pattern(
        self,
        message: DLQMessage
    ) -> bool:
        """Check if errors follow a consistent pattern"""
        if len(message.error_history) < 3:
            return False
        
        # Get last N errors
        recent_errors = message.error_history[-5:]
        
        # Check if all errors are similar
        error_types = [
            self._extract_error_type(err["error"]) 
            for err in recent_errors
        ]
        
        # If all errors are the same type
        return len(set(error_types)) == 1
    
    def _generate_error_pattern_hash(self, error: str) -> str:
        """Generate hash for error pattern"""
        # Extract key parts of error
        error_type = self._extract_error_type(error)
        
        # Create hash
        return hashlib.md5(error_type.encode()).hexdigest()[:8]
    
    def _extract_error_type(self, error: str) -> str:
        """Extract error type from error message"""
        # Simple extraction - customize based on your error format
        if ":" in error:
            return error.split(":")[0].strip()
        
        # Take first few words
        words = error.split()[:3]
        return " ".join(words)
    
    def _get_max_depth(self, obj: Any, depth: int = 0) -> int:
        """Get maximum depth of nested structure"""
        if depth > 20:  # Prevent infinite recursion
            return depth
        
        if isinstance(obj, dict):
            if not obj:
                return depth
            return max(
                self._get_max_depth(v, depth + 1) 
                for v in obj.values()
            )
        elif isinstance(obj, list):
            if not obj:
                return depth
            return max(
                self._get_max_depth(item, depth + 1) 
                for item in obj
            )
        else:
            return depth
    
    def clear_cache(self):
        """Clear detection caches"""
        self._failure_cache.clear()
        self._pattern_cache.clear()