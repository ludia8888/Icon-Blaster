"""Configuration management system"""

import os
from typing import Any, Dict
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache

class DatabaseConfig(BaseSettings):
    """Database configuration"""
    endpoint: str = Field(default="http://localhost:6363", env="TERMINUSDB_ENDPOINT")
    team: str = Field(default="admin", env="TERMINUSDB_TEAM")
    db: str = Field(default="oms_db", env="TERMINUSDB_DB") 
    user: str = Field(default="admin", env="TERMINUSDB_USER")
    key: str = Field(default="root", env="TERMINUSDB_KEY")
    
    class Config:
        env_prefix = "TERMINUSDB_"

class EventConfig(BaseSettings):
    """Event system configuration"""
    broker_url: str = Field(default="redis://localhost:6379", env="EVENT_BROKER_URL")
    max_retries: int = Field(default=3, env="EVENT_MAX_RETRIES")
    retry_delay: int = Field(default=1000, env="EVENT_RETRY_DELAY")
    
    class Config:
        env_prefix = "EVENT_"

class ServiceConfig(BaseSettings):
    """Service-level configuration"""
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    debug: bool = Field(default=False, env="DEBUG")
    environment: str = Field(default="development", env="ENVIRONMENT")
    
    class Config:
        env_prefix = "SERVICE_"

class AppConfig(BaseSettings):
    """Application configuration"""
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    event: EventConfig = Field(default_factory=EventConfig)
    service: ServiceConfig = Field(default_factory=ServiceConfig)
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }

@lru_cache()
def get_config() -> AppConfig:
    """Get cached configuration instance"""
    return AppConfig()