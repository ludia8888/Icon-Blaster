"""
Shared Configuration Module
공통 설정 모듈
"""
import os
from typing import Dict, Any, Optional
from pydantic import BaseSettings

class SharedConfig(BaseSettings):
    """공유 설정"""
    
    # 환경 설정
    environment: str = "development"
    debug: bool = True
    
    # 서비스 설정
    service_name: str = "oms"
    service_version: str = "2.0.0"
    
    # 보안 설정
    secret_key: str = "default-secret-key"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 30
    
    # 데이터베이스 설정
    database_url: str = "http://localhost:6363"
    database_username: str = "admin"
    database_password: str = "root"
    
    # Redis 설정
    redis_url: str = "redis://localhost:6379"
    redis_prefix: str = "oms:"
    
    # 이벤트 설정
    event_retention_days: int = 30
    event_batch_size: int = 100
    
    # 로깅 설정
    log_level: str = "INFO"
    log_format: str = "json"
    
    class Config:
        env_prefix = "OMS_"
        case_sensitive = False

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