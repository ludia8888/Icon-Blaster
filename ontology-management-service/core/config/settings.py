"""
Centralized configuration management for ontology-management-service
Addresses technical debt: hardcoded values scattered throughout codebase
"""
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings"""
    model_config = SettingsConfigDict(env_prefix="DB_")
    
    # SQLite
    sqlite_path: str = Field(default="./data/oms.db", description="SQLite database path")
    
    # PostgreSQL
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_user: str = Field(default="oms", description="PostgreSQL user")
    postgres_password: str = Field(default="", description="PostgreSQL password")
    postgres_database: str = Field(default="oms", description="PostgreSQL database")
    
    # TerminusDB
    terminus_url: str = Field(default="http://localhost:6363", description="TerminusDB URL")
    terminus_user: str = Field(default="admin", description="TerminusDB user")
    terminus_password: str = Field(default="root", description="TerminusDB password")
    terminus_organization: str = Field(default="admin", description="TerminusDB organization")
    terminus_database: str = Field(default="oms", description="TerminusDB database")
    
    # Connection pool
    pool_size: int = Field(default=20, description="Connection pool size")
    max_overflow: int = Field(default=10, description="Max overflow connections")
    pool_timeout: int = Field(default=30, description="Pool timeout in seconds")


class RedisSettings(BaseSettings):
    """Redis configuration settings"""
    model_config = SettingsConfigDict(env_prefix="REDIS_")
    
    url: str = Field(default="redis://localhost:6379/0", description="Redis URL")
    max_connections: int = Field(default=50, description="Max Redis connections")
    socket_timeout: int = Field(default=5, description="Socket timeout in seconds")
    socket_connect_timeout: int = Field(default=5, description="Connect timeout in seconds")
    retry_on_timeout: bool = Field(default=True, description="Retry on timeout")
    
    # Cache settings
    cache_ttl: int = Field(default=300, description="Default cache TTL in seconds")
    lock_ttl: int = Field(default=60, description="Lock TTL in seconds")


class ServiceSettings(BaseSettings):
    """External service configuration"""
    model_config = SettingsConfigDict(env_prefix="SERVICE_")
    
    # IAM Service
    iam_url: str = Field(default="http://user-service:8000", description="IAM service URL")
    iam_verify_ssl: bool = Field(default=True, description="Verify IAM SSL")
    iam_timeout: int = Field(default=30, description="IAM request timeout")
    
    # Audit Service
    audit_url: str = Field(default="http://audit-service:8001", description="Audit service URL")
    audit_enabled: bool = Field(default=True, description="Enable audit logging")
    
    # NATS
    nats_url: str = Field(default="nats://localhost:4222", description="NATS URL")
    nats_cluster_id: str = Field(default="oms-cluster", description="NATS cluster ID")
    
    # WebSocket
    websocket_url: str = Field(default="ws://localhost:8080", description="WebSocket URL")


class ObservabilitySettings(BaseSettings):
    """Observability configuration"""
    model_config = SettingsConfigDict(env_prefix="OBSERVABILITY_")
    
    # OpenTelemetry
    otlp_endpoint: str = Field(default="localhost:4317", description="OTLP endpoint")
    otlp_headers: Optional[str] = Field(default=None, description="OTLP headers")
    service_name: str = Field(default="ontology-management-service", description="Service name")
    
    # Metrics
    metrics_enabled: bool = Field(default=True, description="Enable metrics")
    metrics_port: int = Field(default=9090, description="Metrics port")
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format")
    
    # SIEM
    siem_enabled: bool = Field(default=False, description="Enable SIEM integration")
    siem_endpoint: str = Field(default="http://localhost:8088/services/collector", description="SIEM endpoint")
    kafka_bootstrap_servers: str = Field(default="localhost:9092", description="Kafka servers")


class SecuritySettings(BaseSettings):
    """Security configuration"""
    model_config = SettingsConfigDict(env_prefix="SECURITY_")
    
    # JWT
    jwt_secret: str = Field(default="", description="JWT secret key")
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_issuer: str = Field(default="iam.company", description="JWT issuer")
    jwt_audience: str = Field(default="oms", description="JWT audience")
    access_token_expire_minutes: int = Field(default=30, description="Access token expiry")
    
    # Encryption
    encryption_key: str = Field(default="", description="Data encryption key")
    
    # CORS
    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins")
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials")
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_per_minute: int = Field(default=60, description="Requests per minute")


class ApplicationSettings(BaseSettings):
    """Application configuration"""
    model_config = SettingsConfigDict(env_prefix="APP_")
    
    name: str = Field(default="ontology-management-service", description="Application name")
    version: str = Field(default="1.0.0", description="Application version")
    environment: str = Field(default="development", description="Environment")
    debug: bool = Field(default=False, description="Debug mode")
    
    # API
    api_prefix: str = Field(default="/api/v1", description="API prefix")
    docs_url: str = Field(default="/docs", description="Docs URL")
    openapi_url: str = Field(default="/openapi.json", description="OpenAPI URL")
    
    # Timeouts
    default_timeout: int = Field(default=30, description="Default timeout in seconds")
    long_timeout: int = Field(default=300, description="Long operation timeout")
    
    # Pagination
    default_page_size: int = Field(default=20, description="Default page size")
    max_page_size: int = Field(default=100, description="Max page size")
    
    # Circuit breaker
    circuit_breaker_failure_threshold: int = Field(default=5, description="Failure threshold")
    circuit_breaker_recovery_timeout: int = Field(default=60, description="Recovery timeout")
    circuit_breaker_expected_exception: Optional[str] = Field(default=None, description="Expected exception")


class Settings(BaseSettings):
    """Main settings aggregator"""
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    service: ServiceSettings = Field(default_factory=ServiceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    app: ApplicationSettings = Field(default_factory=ApplicationSettings)
    
    class Config:
        case_sensitive = False
        env_file = ".env"
        env_file_encoding = "utf-8"


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get global settings instance"""
    return settings