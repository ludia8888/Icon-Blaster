"""
Shared Configuration Module
공통 설정 모듈
"""
import os
from typing import Dict, Any, Optional

class SharedConfig:
    """공유 설정"""
    
    def __init__(self):
        # 환경 설정
        self.environment = os.getenv("OMS_ENVIRONMENT", "development")
        self.debug = os.getenv("OMS_DEBUG", "true").lower() == "true"
        
        # 서비스 설정
        self.service_name = os.getenv("OMS_SERVICE_NAME", "oms")
        self.service_version = os.getenv("OMS_SERVICE_VERSION", "2.0.0")
        
        # 보안 설정
        self.secret_key = os.getenv("OMS_SECRET_KEY", "default-secret-key")
        self.jwt_algorithm = os.getenv("OMS_JWT_ALGORITHM", "HS256")
        self.jwt_expiration_minutes = int(os.getenv("OMS_JWT_EXPIRATION_MINUTES", "30"))
        
        # 데이터베이스 설정
        self.database_url = os.getenv("OMS_DATABASE_URL", "http://localhost:6363")
        self.database_username = os.getenv("OMS_DATABASE_USERNAME", "admin")
        self.database_password = os.getenv("OMS_DATABASE_PASSWORD", "root")
        
        # Redis 설정
        self.redis_url = os.getenv("OMS_REDIS_URL", "redis://localhost:6379")
        self.redis_prefix = os.getenv("OMS_REDIS_PREFIX", "oms:")
        
        # 이벤트 설정
        self.event_retention_days = int(os.getenv("OMS_EVENT_RETENTION_DAYS", "30"))
        self.event_batch_size = int(os.getenv("OMS_EVENT_BATCH_SIZE", "100"))
        
        # 로깅 설정
        self.log_level = os.getenv("OMS_LOG_LEVEL", "INFO")
        self.log_format = os.getenv("OMS_LOG_FORMAT", "json")

# 전역 설정 인스턴스
_config = None

def get_config() -> SharedConfig:
    """설정 인스턴스 반환"""
    global _config
    if _config is None:
        _config = SharedConfig()
    return _config

# Convenience exports
config = get_config()