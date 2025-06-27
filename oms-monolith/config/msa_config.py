"""
Microservice Architecture Configuration
Central configuration for all MSA integrations
"""
import os
from typing import Dict, Optional
from pydantic import BaseSettings, Field


class ServiceEndpoint(BaseSettings):
    """Configuration for a microservice endpoint"""
    url: str
    timeout: int = 10
    retry_count: int = 3
    health_endpoint: str = "/health"
    use_ssl: bool = False
    api_key: Optional[str] = None


class MSAConfig(BaseSettings):
    """
    Master configuration for MSA integration
    Supports both environment variables and configuration files
    """
    
    # Service Discovery
    service_discovery_enabled: bool = Field(
        default=False,
        env="SERVICE_DISCOVERY_ENABLED"
    )
    consul_url: Optional[str] = Field(
        default="http://consul:8500",
        env="CONSUL_URL"
    )
    
    # IAM Service
    iam_service_url: str = Field(
        default="http://user-service:8000",
        env="IAM_SERVICE_URL"
    )
    iam_jwks_url: Optional[str] = Field(
        default=None,
        env="IAM_JWKS_URL"
    )
    iam_service_id: str = Field(
        default="oms-service",
        env="IAM_SERVICE_ID"
    )
    iam_service_secret: Optional[str] = Field(
        default=None,
        env="IAM_SERVICE_SECRET"
    )
    
    # Audit Service
    audit_service_url: str = Field(
        default="http://audit-service:8001",
        env="AUDIT_SERVICE_URL"
    )
    audit_service_enabled: bool = Field(
        default=True,
        env="AUDIT_SERVICE_ENABLED"
    )
    
    # Notification Service
    notification_service_url: str = Field(
        default="http://notification-service:8002",
        env="NOTIFICATION_SERVICE_URL"
    )
    
    # Search Service
    search_service_url: str = Field(
        default="http://search-service:8003",
        env="SEARCH_SERVICE_URL"
    )
    
    # Common Settings
    service_timeout: int = Field(
        default=10,
        env="SERVICE_TIMEOUT"
    )
    service_retry_count: int = Field(
        default=3,
        env="SERVICE_RETRY_COUNT"
    )
    
    # Circuit Breaker
    circuit_breaker_enabled: bool = Field(
        default=True,
        env="CIRCUIT_BREAKER_ENABLED"
    )
    circuit_breaker_failure_threshold: int = Field(
        default=5,
        env="CIRCUIT_BREAKER_FAILURE_THRESHOLD"
    )
    circuit_breaker_recovery_timeout: int = Field(
        default=60,
        env="CIRCUIT_BREAKER_RECOVERY_TIMEOUT"
    )
    
    # Tracing
    tracing_enabled: bool = Field(
        default=False,
        env="TRACING_ENABLED"
    )
    jaeger_agent_host: str = Field(
        default="jaeger",
        env="JAEGER_AGENT_HOST"
    )
    jaeger_agent_port: int = Field(
        default=6831,
        env="JAEGER_AGENT_PORT"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    def get_service_endpoints(self) -> Dict[str, ServiceEndpoint]:
        """Get all configured service endpoints"""
        return {
            "iam": ServiceEndpoint(
                url=self.iam_service_url,
                timeout=self.service_timeout,
                retry_count=self.service_retry_count
            ),
            "audit": ServiceEndpoint(
                url=self.audit_service_url,
                timeout=self.service_timeout,
                retry_count=self.service_retry_count
            ),
            "notification": ServiceEndpoint(
                url=self.notification_service_url,
                timeout=self.service_timeout,
                retry_count=self.service_retry_count
            ),
            "search": ServiceEndpoint(
                url=self.search_service_url,
                timeout=self.service_timeout,
                retry_count=self.service_retry_count
            )
        }
    
    def get_iam_config(self) -> Dict[str, any]:
        """Get IAM-specific configuration"""
        return {
            "iam_service_url": self.iam_service_url,
            "jwks_url": self.iam_jwks_url,
            "service_id": self.iam_service_id,
            "service_secret": self.iam_service_secret,
            "timeout": self.service_timeout,
            "retry_count": self.service_retry_count
        }


# Global configuration instance
_msa_config: Optional[MSAConfig] = None


def get_msa_config() -> MSAConfig:
    """Get global MSA configuration"""
    global _msa_config
    if _msa_config is None:
        _msa_config = MSAConfig()
    return _msa_config


# Environment-specific configurations
def get_environment_config() -> Dict[str, any]:
    """Get environment-specific configuration"""
    env = os.getenv("ENVIRONMENT", "development")
    
    configs = {
        "development": {
            "iam_service_url": "http://localhost:8000",
            "audit_service_url": "http://localhost:8001",
            "service_discovery_enabled": False,
            "circuit_breaker_enabled": False,
            "tracing_enabled": False
        },
        "staging": {
            "iam_service_url": "http://user-service:8000",
            "audit_service_url": "http://audit-service:8001",
            "service_discovery_enabled": True,
            "circuit_breaker_enabled": True,
            "tracing_enabled": True
        },
        "production": {
            "iam_service_url": "https://iam.company.com",
            "audit_service_url": "https://audit.company.com",
            "service_discovery_enabled": True,
            "circuit_breaker_enabled": True,
            "tracing_enabled": True,
            "use_ssl": True
        }
    }
    
    return configs.get(env, configs["development"])