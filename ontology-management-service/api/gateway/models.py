"""
API Gateway 도메인 모델
API Gateway 관련 모델 정의
"""
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class AuthMethod(str, Enum):
    """인증 방법"""
    JWT = "jwt"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    BASIC = "basic"


class RateLimitPolicy(BaseModel):
    """Rate Limit 정책"""
    requests_per_minute: int
    requests_per_hour: Optional[int] = None
    requests_per_day: Optional[int] = None
    burst_size: int = Field(default=10, description="Burst 허용량")
    by_user: bool = Field(default=True, description="사용자별 제한 여부")
    by_ip: bool = Field(default=False, description="IP별 제한 여부")


class ServiceRoute(BaseModel):
    """서비스 라우트"""
    path_pattern: str
    service_name: str
    service_url: str
    methods: List[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE"])
    strip_prefix: bool = True
    timeout: int = Field(default=30, description="Timeout in seconds")
    retry_count: int = Field(default=3)
    circuit_breaker_enabled: bool = True


class AuthConfig(BaseModel):
    """인증 설정"""
    enabled: bool = True
    methods: List[AuthMethod] = Field(default_factory=lambda: [AuthMethod.JWT])
    jwt_secret: Optional[str] = None
    jwt_issuer: Optional[str] = None
    api_key_header: str = "X-API-Key"
    exclude_paths: List[str] = Field(default_factory=lambda: ["/health", "/metrics"])


class CorsConfig(BaseModel):
    """CORS 설정"""
    enabled: bool = True
    allowed_origins: List[str] = Field(default_factory=lambda: ["*"])
    allowed_methods: List[str] = Field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    allowed_headers: List[str] = Field(default_factory=lambda: ["*"])
    expose_headers: List[str] = Field(default_factory=list)
    allow_credentials: bool = True
    max_age: int = 3600


class GatewayConfig(BaseModel):
    """API Gateway 전체 설정"""
    routes: List[ServiceRoute]
    auth: AuthConfig
    cors: CorsConfig
    rate_limit: RateLimitPolicy
    enable_metrics: bool = True
    enable_tracing: bool = True
    log_requests: bool = True


class RequestContext(BaseModel):
    """요청 컨텍스트"""
    request_id: str
    user_id: Optional[str] = None
    user_roles: List[str] = Field(default_factory=list)
    client_ip: str
    user_agent: Optional[str] = None
    auth_method: Optional[AuthMethod] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    headers: Dict[str, str] = Field(default_factory=dict)


class GatewayMetrics(BaseModel):
    """Gateway 메트릭"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0
    requests_by_service: Dict[str, int] = Field(default_factory=dict)
    requests_by_method: Dict[str, int] = Field(default_factory=dict)
    rate_limit_hits: int = 0
    auth_failures: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
