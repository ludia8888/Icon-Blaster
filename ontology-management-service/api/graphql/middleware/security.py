"""
Lightweight Security Middleware for GraphQL
Only loaded when ENABLE_GQL_SECURITY=true
"""
import time
from typing import Dict, Any, Optional
from collections import defaultdict
from datetime import datetime, timedelta

import strawberry
from strawberry.types import Info
from graphql import GraphQLError

from common_logging.setup import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Simple in-memory rate limiter"""
    def __init__(self, requests: int = 100, window: int = 60):
        self.requests = requests
        self.window = window
        self.clients: Dict[str, list] = defaultdict(list)
    
    def is_allowed(self, client_id: str) -> bool:
        now = time.time()
        # Clean old entries
        self.clients[client_id] = [
            ts for ts in self.clients[client_id] 
            if ts > now - self.window
        ]
        
        if len(self.clients[client_id]) >= self.requests:
            return False
            
        self.clients[client_id].append(now)
        return True


class SecurityValidator:
    """Lightweight query security validator"""
    
    def __init__(self, config):
        self.config = config
        self.rate_limiter = RateLimiter(
            config.rate_limit_requests,
            config.rate_limit_window
        ) if config.enable_security else None
    
    def validate_query_depth(self, query_ast, depth: int = 0) -> int:
        """Calculate query depth"""
        if not hasattr(query_ast, 'selection_set') or not query_ast.selection_set:
            return depth
            
        max_depth = depth
        for selection in query_ast.selection_set.selections:
            field_depth = self.validate_query_depth(selection, depth + 1)
            max_depth = max(max_depth, field_depth)
            
        return max_depth
    
    def check_rate_limit(self, client_id: str) -> bool:
        """Check if client exceeded rate limit"""
        if not self.rate_limiter:
            return True
        return self.rate_limiter.is_allowed(client_id)


def create_security_extension(config):
    """Create security extension for Strawberry"""
    if not config.enable_security:
        return None
        
    validator = SecurityValidator(config)
    
    class SecurityExtension(strawberry.extensions.Extension):
        def on_request_start(self):
            # Extract client ID from request
            request = self.execution_context.context.get("request")
            if request:
                client_id = request.client.host or "anonymous"
                
                # Rate limiting
                if not validator.check_rate_limit(client_id):
                    raise GraphQLError(
                        f"Rate limit exceeded. Max {config.rate_limit_requests} requests per {config.rate_limit_window}s"
                    )
        
        def on_parsing_start(self):
            # Query depth validation would go here
            pass
    
    return SecurityExtension