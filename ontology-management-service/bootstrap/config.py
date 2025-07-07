"""Configuration management system"""

import os
from typing import Any, Dict, Optional, Type
from pydantic_settings import BaseSettings, SettingsConfigDict, PydanticBaseSettingsSource
from pydantic import Field
from functools import lru_cache
import yaml
import json

class YamlConfigSettingsSource(PydanticBaseSettingsSource):
    """
    A settings source that loads variables from a YAML file
    at a specified path.
    """
    def __init__(self, settings_cls: Type[BaseSettings], yaml_file_path: str):
        super().__init__(settings_cls)
        self.yaml_file_path = yaml_file_path

    def get_field_value(self, field, field_name):
        # This source is designed to load a whole file content into one field
        return None

    def __call__(self) -> Dict[str, Any]:
        if not os.path.exists(self.yaml_file_path):
            return {}
        with open(self.yaml_file_path, 'r') as f:
            return yaml.safe_load(f) or {}

class TerminusDBConfig(BaseSettings):
    """TerminusDB configuration"""
    endpoint: str = Field(default="http://localhost:6363", validation_alias="TERMINUSDB_ENDPOINT")
    team: str = Field(default="admin", validation_alias="TERMINUSDB_TEAM")
    db: str = Field(default="oms_db", validation_alias="TERMINUSDB_DB") 
    user: str = Field(default="admin", validation_alias="TERMINUSDB_USER")
    key: str = Field(default="root", validation_alias="TERMINUSDB_KEY")
    
    model_config = SettingsConfigDict(env_prefix="TERMINUSDB_")

class PostgresConfig(BaseSettings):
    """PostgreSQL configuration"""
    host: str = Field(default="localhost", validation_alias="POSTGRES_HOST")
    port: int = Field(default=5432, validation_alias="POSTGRES_PORT")
    user: str = Field(default="postgres", validation_alias="POSTGRES_USER")
    password: str = Field(default="", validation_alias="POSTGRES_PASSWORD")
    database: str = Field(default="oms_db", validation_alias="POSTGRES_DB")

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")

class SQLiteConfig(BaseSettings):
    """SQLite configuration"""
    db_name: str = Field(default="oms_fallback.db", validation_alias="SQLITE_DB_NAME")
    db_dir: str = Field(default="data", validation_alias="SQLITE_DB_DIR")

    model_config = SettingsConfigDict(env_prefix="SQLITE_")

class EventConfig(BaseSettings):
    """Event system configuration"""
    broker_url: str = Field(default="redis://localhost:6379", validation_alias="EVENT_BROKER_URL")
    max_retries: int = Field(default=3, validation_alias="EVENT_MAX_RETRIES")
    retry_delay: int = Field(default=1000, validation_alias="EVENT_RETRY_DELAY")
    
    model_config = SettingsConfigDict(env_prefix="EVENT_")

class ServiceConfig(BaseSettings):
    """Service-level configuration"""
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    resilience_timeout: float = Field(default=0.5, validation_alias="RESILIENCE_TIMEOUT", description="Default timeout in seconds for resilient operations")
    
    model_config = SettingsConfigDict(env_prefix="SERVICE_")

class UserServiceConfig(BaseSettings):
    """User Service configuration"""
    url: str = Field(default="http://user-service:8000", validation_alias="USER_SERVICE_URL")

    model_config = SettingsConfigDict(env_prefix="USER_SERVICE_")

class LockConfig(BaseSettings):
    """Distributed Lock configuration"""
    backend: str = Field(default="redis", validation_alias="LOCK_BACKEND", description="Lock backend (redis, memory)")
    redis_url: str = Field(default="redis://localhost:6379/1", validation_alias="LOCK_REDIS_URL")
    namespace: str = Field(default="oms:locks", validation_alias="LOCK_NAMESPACE")
    ttl: int = Field(default=300, validation_alias="LOCK_TTL_SECONDS", description="Default lock TTL in seconds")
    max_wait: int = Field(default=30, validation_alias="LOCK_MAX_WAIT_SECONDS", description="Max time to wait for a lock")

    model_config = SettingsConfigDict(env_prefix="LOCK_")

class RedisConfig(BaseSettings):
    """Redis configuration"""
    host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")
    db: int = Field(default=0, validation_alias="REDIS_DB")
    password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")
    username: Optional[str] = Field(default=None, validation_alias="REDIS_USERNAME")
    ssl: bool = Field(default=False, validation_alias="REDIS_SSL")
    
    # Connection pool settings
    max_connections: int = Field(default=50, validation_alias="REDIS_MAX_CONNECTIONS")
    socket_timeout: float = Field(default=5.0, validation_alias="REDIS_SOCKET_TIMEOUT")
    
    # Cluster/Sentinel settings
    cluster_mode: bool = Field(default=False, validation_alias="REDIS_CLUSTER_MODE")
    sentinel_mode: bool = Field(default=False, validation_alias="REDIS_SENTINEL_MODE")
    sentinel_service: str = Field(default="mymaster", validation_alias="REDIS_SENTINEL_SERVICE")

    model_config = SettingsConfigDict(env_prefix="REDIS_")

class AppConfig(BaseSettings):
    """Application configuration"""
    terminusdb: Optional[TerminusDBConfig] = Field(default_factory=TerminusDBConfig)
    postgres: Optional[PostgresConfig] = Field(default_factory=PostgresConfig)
    sqlite: Optional[SQLiteConfig] = Field(default_factory=SQLiteConfig)
    
    event: EventConfig = Field(default_factory=EventConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    user_service: UserServiceConfig = Field(default_factory=UserServiceConfig)
    lock: LockConfig = Field(default_factory=LockConfig)
    redis: Optional[RedisConfig] = Field(default_factory=RedisConfig)
    scope_mapping: Dict[str, Any] = Field(default_factory=dict)
    
    def __init__(self, **values: Any):
        super().__init__(**values)
        self._load_yaml_configs()

    def _load_yaml_configs(self):
        """Load additional configurations from YAML files."""
        # Load scope mapping
        scope_config_path = "config/scope_mapping.yaml"
        if os.path.exists(scope_config_path):
            with open(scope_config_path, 'r') as f:
                self.scope_mapping = yaml.safe_load(f) or {}

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_config() -> AppConfig:
    """Get cached configuration instance"""
    return AppConfig()