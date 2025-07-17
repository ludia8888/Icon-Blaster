"""
서비스 설정 데이터클래스 정의
각 서비스에 필요한 설정을 담당
SRP: 오직 설정 데이터 구조만 담당
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import sys
import os

# shared import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'shared'))
from models.config import ConnectionConfig
from utils.serialization import SerializableMixin


@dataclass
class CacheConfig(SerializableMixin):
    """캐시 설정"""
    
    enabled: bool = True
    ttl: int = 300  # 5분
    max_size: int = 1000
    eviction_policy: str = "lru"  # lru, lfu, fifo
    
    # to_dict() method는 SerializableMixin에서 자동 제공됨


@dataclass
class LoggingConfig(SerializableMixin):
    """로깅 설정"""
    
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    file: Optional[str] = None
    max_bytes: int = 10485760  # 10MB
    backup_count: int = 5
    
    # to_dict() method는 SerializableMixin에서 자동 제공됨


@dataclass
class SecurityConfig(SerializableMixin):
    """보안 설정"""
    
    enable_auth: bool = True
    enable_rbac: bool = False
    enable_audit: bool = True
    encrypt_data: bool = False
    allowed_origins: list = field(default_factory=lambda: ["*"])
    max_request_size: int = 10485760  # 10MB
    
    # to_dict() method는 SerializableMixin에서 자동 제공됨


@dataclass
class ServiceConfig(SerializableMixin):
    """전체 서비스 설정"""
    
    app_name: str = "Ontology BFF"
    version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True
    
    # 하위 설정
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    
    # 추가 설정
    label_mapper_db: str = "../data/label_mappings.db"
    default_language: str = "ko"
    supported_languages: list = field(default_factory=lambda: ["ko", "en", "ja", "zh"])
    
    # to_dict() method는 SerializableMixin에서 자동 제공됨 (중첩 오브젝트 지원)
    
    @classmethod
    def from_env(cls) -> 'ServiceConfig':
        """환경 변수에서 설정 로드"""
        import os
        
        config = cls()
        
        # 환경 변수 매핑
        config.environment = os.getenv("ENVIRONMENT", config.environment)
        config.debug = os.getenv("DEBUG", str(config.debug)).lower() == "true"
        
        # 연결 설정
        config.connection.server_url = os.getenv("TERMINUS_URL", config.connection.server_url)
        config.connection.user = os.getenv("TERMINUS_USER", config.connection.user)
        config.connection.key = os.getenv("TERMINUS_KEY", config.connection.key)
        
        # 캐시 설정
        config.cache.enabled = os.getenv("CACHE_ENABLED", str(config.cache.enabled)).lower() == "true"
        config.cache.ttl = int(os.getenv("CACHE_TTL", str(config.cache.ttl)))
        
        # 로깅 설정
        config.logging.level = os.getenv("LOG_LEVEL", config.logging.level)
        config.logging.file = os.getenv("LOG_FILE", config.logging.file)
        
        # 보안 설정
        config.security.enable_auth = os.getenv("ENABLE_AUTH", str(config.security.enable_auth)).lower() == "true"
        config.security.enable_rbac = os.getenv("ENABLE_RBAC", str(config.security.enable_rbac)).lower() == "true"
        
        return config