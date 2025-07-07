"""
Rate limiting data models
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


class RateLimitAlgorithm(Enum):
    """Rate limiting algorithms"""
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"
    ADAPTIVE = "adaptive"


class RateLimitScope(Enum):
    """Rate limit scopes"""
    GLOBAL = "global"
    USER = "user"
    IP = "ip"
    ENDPOINT = "endpoint"
    COMBINED = "combined"


@dataclass
class RateLimitKey:
    """Key for rate limit tracking"""
    scope: RateLimitScope
    identifier: str
    endpoint: Optional[str] = None
    
    def to_string(self) -> str:
        """Convert to string key"""
        parts = [self.scope.value, self.identifier]
        if self.endpoint:
            parts.append(self.endpoint)
        return ":".join(parts)


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""
    # Basic settings
    requests_per_window: int = 100
    window_seconds: int = 60
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW
    scope: RateLimitScope = RateLimitScope.USER
    
    # Algorithm-specific settings
    burst_size: Optional[int] = None  # For token bucket
    refill_rate: Optional[float] = None  # For token/leaky bucket
    
    # Adaptive settings
    adaptive_enabled: bool = False
    min_requests: int = 10
    max_requests: int = 1000
    scale_factor: float = 1.5
    
    # Override settings
    whitelist: List[str] = field(default_factory=list)
    blacklist: List[str] = field(default_factory=list)
    custom_limits: Dict[str, int] = field(default_factory=dict)
    
    def get_limit_for(self, identifier: str) -> int:
        """Get rate limit for specific identifier"""
        if identifier in self.whitelist:
            return float('inf')
        if identifier in self.blacklist:
            return 0
        if identifier in self.custom_limits:
            return self.custom_limits[identifier]
        return self.requests_per_window


@dataclass
class RateLimitResult:
    """Result of rate limit check"""
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: Optional[int] = None  # Seconds until retry
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get rate limit headers for HTTP response"""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(int(self.reset_at.timestamp()))
        }
        
        if not self.allowed and self.retry_after:
            headers["Retry-After"] = str(self.retry_after)
        
        return headers


@dataclass
class RateLimitMetrics:
    """Metrics for rate limiting"""
    total_requests: int = 0
    allowed_requests: int = 0
    denied_requests: int = 0
    unique_identifiers: int = 0
    last_reset: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def denial_rate(self) -> float:
        """Calculate request denial rate"""
        if self.total_requests == 0:
            return 0.0
        return (self.denied_requests / self.total_requests) * 100
    
    def record_request(self, allowed: bool):
        """Record a request"""
        self.total_requests += 1
        if allowed:
            self.allowed_requests += 1
        else:
            self.denied_requests += 1


@dataclass
class RateLimitState:
    """State for rate limit tracking"""
    count: int = 0
    window_start: datetime = field(default_factory=datetime.utcnow)
    tokens: float = 0.0  # For token bucket
    last_update: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "count": self.count,
            "window_start": self.window_start.isoformat(),
            "tokens": self.tokens,
            "last_update": self.last_update.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RateLimitState":
        """Create from dictionary"""
        return cls(
            count=data.get("count", 0),
            window_start=datetime.fromisoformat(data["window_start"]),
            tokens=data.get("tokens", 0.0),
            last_update=datetime.fromisoformat(data["last_update"])
        )