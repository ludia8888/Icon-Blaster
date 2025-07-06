"""
GraphQL Service Configuration with Feature Flags
"""
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class GraphQLConfig:
    """Feature flags and configuration for GraphQL service"""
    
    # Feature Flags
    enable_security: bool = False
    enable_cache: bool = False
    enable_tracing: bool = False
    enable_introspection: bool = True
    
    # Security Settings
    max_query_depth: int = 15
    max_query_complexity: int = 2000
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds
    
    # Cache Settings
    cache_ttl: int = 300  # seconds
    cache_key_prefix: str = "gql:"
    
    # Tracing Settings
    trace_sample_rate: float = 0.1
    
    @classmethod
    def from_env(cls) -> "GraphQLConfig":
        """Load configuration from environment variables"""
        env = os.getenv("APP_ENV", "development")
        
        # Default configurations per environment
        if env == "production":
            return cls(
                enable_security=os.getenv("ENABLE_GQL_SECURITY", "true").lower() == "true",
                enable_cache=os.getenv("ENABLE_GQL_CACHE", "true").lower() == "true",
                enable_tracing=os.getenv("ENABLE_GQL_TRACING", "true").lower() == "true",
                enable_introspection=False,
                max_query_depth=int(os.getenv("GQL_MAX_DEPTH", "10")),
                max_query_complexity=int(os.getenv("GQL_MAX_COMPLEXITY", "1000")),
                trace_sample_rate=float(os.getenv("TRACE_SAMPLE_RATE", "0.1"))
            )
        elif env == "staging":
            return cls(
                enable_security=os.getenv("ENABLE_GQL_SECURITY", "true").lower() == "true",
                enable_cache=os.getenv("ENABLE_GQL_CACHE", "true").lower() == "true",
                enable_tracing=os.getenv("ENABLE_GQL_TRACING", "true").lower() == "true",
                enable_introspection=True,
                trace_sample_rate=1.0  # Full tracing in staging
            )
        else:  # development/test
            return cls(
                enable_security=os.getenv("ENABLE_GQL_SECURITY", "false").lower() == "true",
                enable_cache=os.getenv("ENABLE_GQL_CACHE", "false").lower() == "true",
                enable_tracing=os.getenv("ENABLE_GQL_TRACING", "false").lower() == "true",
                enable_introspection=True
            )


# Global config instance
graphql_config = GraphQLConfig.from_env()