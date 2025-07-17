"""
Production-Grade Environment Variable Validation
Provides comprehensive validation and configuration management for environment variables
"""

import os
import re
import logging
from typing import Dict, Any, Optional, List, Union, Callable
from enum import Enum
from dataclasses import dataclass
from pydantic import BaseModel, Field, validator
import socket

logger = logging.getLogger(__name__)


class EnvType(Enum):
    """Environment variable types for validation"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    URL = "url"
    HOST = "host"
    PORT = "port"
    EMAIL = "email"
    PATH = "path"
    JSON = "json"
    CSV = "csv"


@dataclass
class EnvVarConfig:
    """Configuration for environment variable validation"""
    name: str
    env_type: EnvType
    required: bool = True
    default: Optional[Any] = None
    description: str = ""
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    choices: Optional[List[str]] = None
    validator_func: Optional[Callable[[Any], bool]] = None
    sensitive: bool = False  # Whether to mask value in logs


class EnvironmentConfig(BaseModel):
    """Validated environment configuration model"""
    
    # Core service configuration
    environment: str = Field(..., description="Deployment environment")
    debug: bool = Field(False, description="Debug mode flag")
    log_level: str = Field("INFO", description="Logging level")
    
    # Service endpoints
    oms_base_url: str = Field(..., description="OMS service base URL")
    bff_port: int = Field(8002, description="BFF service port")
    oms_port: int = Field(8000, description="OMS service port")
    
    # Database configuration
    database_url: Optional[str] = Field(None, description="Database connection URL")
    redis_url: Optional[str] = Field(None, description="Redis connection URL")
    terminusdb_url: str = Field("http://localhost:6363", description="TerminusDB URL")
    terminusdb_user: str = Field("admin", description="TerminusDB username")
    terminusdb_password: str = Field("root", description="TerminusDB password")
    
    # Security configuration
    secret_key: Optional[str] = Field(None, description="Application secret key")
    jwt_secret: Optional[str] = Field(None, description="JWT signing secret")
    cors_origins: str = Field("*", description="CORS allowed origins")
    
    # Monitoring configuration
    enable_metrics: bool = Field(True, description="Enable metrics collection")
    metrics_port: Optional[int] = Field(None, description="Metrics server port")
    
    # Rate limiting
    rate_limit_requests: int = Field(100, description="Max requests per minute")
    rate_limit_burst: int = Field(50, description="Rate limit burst size")
    
    @validator('environment')
    def validate_environment(cls, v):
        valid_envs = ['development', 'testing', 'staging', 'production']
        if v.lower() not in valid_envs:
            raise ValueError(f"Environment must be one of: {valid_envs}")
        return v.lower()
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()
    
    @validator('oms_base_url', 'database_url', 'redis_url', 'terminusdb_url')
    def validate_urls(cls, v):
        if v and not v.startswith(('http://', 'https://', 'postgresql://', 'redis://')):
            raise ValueError(f"Invalid URL format: {v}")
        return v
    
    @validator('bff_port', 'oms_port', 'metrics_port')
    def validate_ports(cls, v):
        if v is not None and (v < 1 or v > 65535):
            raise ValueError(f"Port must be between 1 and 65535: {v}")
        return v


class EnvironmentValidator:
    """
    Production-grade environment variable validator
    
    Features:
    - Type validation and conversion
    - Range and format validation
    - Security-conscious handling of sensitive values
    - Comprehensive error reporting
    - Configuration validation
    """
    
    def __init__(self):
        self.config_definitions = self._define_config_schema()
        self.validation_errors = []
        self.warnings = []
    
    def _define_config_schema(self) -> List[EnvVarConfig]:
        """Define the complete environment variable schema"""
        return [
            # Core service configuration
            EnvVarConfig(
                name="ENVIRONMENT",
                env_type=EnvType.STRING,
                required=True,
                default="development",
                description="Deployment environment (development, testing, staging, production)",
                choices=["development", "testing", "staging", "production"]
            ),
            EnvVarConfig(
                name="DEBUG",
                env_type=EnvType.BOOLEAN,
                required=False,
                default=False,
                description="Enable debug mode"
            ),
            EnvVarConfig(
                name="LOG_LEVEL",
                env_type=EnvType.STRING,
                required=False,
                default="INFO",
                description="Logging level",
                choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            ),
            
            # Service endpoints
            EnvVarConfig(
                name="OMS_BASE_URL",
                env_type=EnvType.URL,
                required=True,
                default="http://localhost:8000",
                description="OMS service base URL"
            ),
            EnvVarConfig(
                name="BFF_PORT",
                env_type=EnvType.PORT,
                required=False,
                default=8002,
                description="BFF service port",
                min_value=1,
                max_value=65535
            ),
            EnvVarConfig(
                name="OMS_PORT",
                env_type=EnvType.PORT,
                required=False,
                default=8000,
                description="OMS service port",
                min_value=1,
                max_value=65535
            ),
            
            # Database configuration
            EnvVarConfig(
                name="DATABASE_URL",
                env_type=EnvType.URL,
                required=False,
                description="Database connection URL",
                sensitive=True
            ),
            EnvVarConfig(
                name="REDIS_URL",
                env_type=EnvType.URL,
                required=False,
                description="Redis connection URL",
                sensitive=True
            ),
            EnvVarConfig(
                name="TERMINUSDB_URL",
                env_type=EnvType.URL,
                required=False,
                default="http://localhost:6363",
                description="TerminusDB service URL"
            ),
            EnvVarConfig(
                name="TERMINUSDB_USER",
                env_type=EnvType.STRING,
                required=False,
                default="admin",
                description="TerminusDB username",
                min_length=1,
                max_length=50
            ),
            EnvVarConfig(
                name="TERMINUSDB_PASSWORD",
                env_type=EnvType.STRING,
                required=False,
                default="root",
                description="TerminusDB password",
                sensitive=True,
                min_length=1
            ),
            
            # Security configuration
            EnvVarConfig(
                name="SECRET_KEY",
                env_type=EnvType.STRING,
                required=False,
                description="Application secret key",
                sensitive=True,
                min_length=32,
                validator_func=self._validate_secret_key
            ),
            EnvVarConfig(
                name="JWT_SECRET",
                env_type=EnvType.STRING,
                required=False,
                description="JWT signing secret",
                sensitive=True,
                min_length=32
            ),
            EnvVarConfig(
                name="CORS_ORIGINS",
                env_type=EnvType.STRING,
                required=False,
                default="*",
                description="CORS allowed origins (comma-separated)"
            ),
            
            # Monitoring configuration
            EnvVarConfig(
                name="ENABLE_METRICS",
                env_type=EnvType.BOOLEAN,
                required=False,
                default=True,
                description="Enable metrics collection"
            ),
            EnvVarConfig(
                name="METRICS_PORT",
                env_type=EnvType.PORT,
                required=False,
                description="Metrics server port",
                min_value=1024,
                max_value=65535
            ),
            
            # Rate limiting
            EnvVarConfig(
                name="RATE_LIMIT_REQUESTS",
                env_type=EnvType.INTEGER,
                required=False,
                default=100,
                description="Max requests per minute",
                min_value=1,
                max_value=10000
            ),
            EnvVarConfig(
                name="RATE_LIMIT_BURST",
                env_type=EnvType.INTEGER,
                required=False,
                default=50,
                description="Rate limit burst size",
                min_value=1,
                max_value=1000
            ),
        ]
    
    def validate_environment(self) -> EnvironmentConfig:
        """Validate all environment variables and return configuration"""
        self.validation_errors = []
        self.warnings = []
        
        validated_config = {}
        
        # Validate each defined environment variable
        for env_config in self.config_definitions:
            try:
                value = self._validate_env_var(env_config)
                validated_config[env_config.name.lower()] = value
            except Exception as e:
                self.validation_errors.append(f"{env_config.name}: {str(e)}")
        
        # Check for critical errors
        if self.validation_errors:
            error_msg = "Environment validation failed:\n" + "\n".join(self.validation_errors)
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Log warnings
        if self.warnings:
            for warning in self.warnings:
                logger.warning(warning)
        
        # Create and validate the configuration model
        try:
            config = EnvironmentConfig(**validated_config)
            self._perform_additional_validations(config)
            
            # Log successful validation
            logger.info("Environment validation successful")
            self._log_configuration_summary(config)
            
            return config
            
        except Exception as e:
            logger.error(f"Configuration model validation failed: {e}")
            raise ValueError(f"Configuration validation failed: {e}")
    
    def _validate_env_var(self, config: EnvVarConfig) -> Any:
        """Validate a single environment variable"""
        value = os.getenv(config.name)
        
        # Handle missing values
        if value is None:
            if config.required:
                raise ValueError(f"Required environment variable '{config.name}' is not set")
            else:
                return config.default
        
        # Type conversion and validation
        try:
            converted_value = self._convert_value(value, config.env_type)
            self._validate_constraints(converted_value, config)
            return converted_value
        except Exception as e:
            raise ValueError(f"Invalid value for {config.name}: {str(e)}")
    
    def _convert_value(self, value: str, env_type: EnvType) -> Any:
        """Convert string value to appropriate type"""
        if env_type == EnvType.STRING:
            return value
        elif env_type == EnvType.INTEGER:
            return int(value)
        elif env_type == EnvType.FLOAT:
            return float(value)
        elif env_type == EnvType.BOOLEAN:
            return value.lower() in ('true', '1', 'yes', 'on', 'enabled')
        elif env_type == EnvType.URL:
            return self._validate_url(value)
        elif env_type == EnvType.HOST:
            return self._validate_host(value)
        elif env_type == EnvType.PORT:
            port = int(value)
            if port < 1 or port > 65535:
                raise ValueError(f"Port must be between 1 and 65535: {port}")
            return port
        elif env_type == EnvType.EMAIL:
            return self._validate_email(value)
        elif env_type == EnvType.PATH:
            return self._validate_path(value)
        elif env_type == EnvType.JSON:
            import json
            return json.loads(value)
        elif env_type == EnvType.CSV:
            return [item.strip() for item in value.split(',') if item.strip()]
        else:
            raise ValueError(f"Unknown environment type: {env_type}")
    
    def _validate_constraints(self, value: Any, config: EnvVarConfig):
        """Validate value against constraints"""
        
        # Range validation
        if config.min_value is not None and value < config.min_value:
            raise ValueError(f"Value {value} is below minimum {config.min_value}")
        if config.max_value is not None and value > config.max_value:
            raise ValueError(f"Value {value} is above maximum {config.max_value}")
        
        # Length validation
        if isinstance(value, str):
            if config.min_length is not None and len(value) < config.min_length:
                raise ValueError(f"Value length {len(value)} is below minimum {config.min_length}")
            if config.max_length is not None and len(value) > config.max_length:
                raise ValueError(f"Value length {len(value)} is above maximum {config.max_length}")
        
        # Pattern validation
        if config.pattern and isinstance(value, str):
            if not re.match(config.pattern, value):
                raise ValueError(f"Value does not match required pattern: {config.pattern}")
        
        # Choice validation
        if config.choices and value not in config.choices:
            raise ValueError(f"Value must be one of: {config.choices}")
        
        # Custom validator
        if config.validator_func and not config.validator_func(value):
            raise ValueError("Value failed custom validation")
    
    def _validate_url(self, url: str) -> str:
        """Validate URL format"""
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
            r'localhost|'  # localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
        
        if not url_pattern.match(url):
            raise ValueError(f"Invalid URL format: {url}")
        return url
    
    def _validate_host(self, host: str) -> str:
        """Validate hostname or IP address"""
        try:
            socket.gethostbyname(host)
            return host
        except socket.gaierror:
            raise ValueError(f"Invalid hostname: {host}")
    
    def _validate_email(self, email: str) -> str:
        """Validate email format"""
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        if not email_pattern.match(email):
            raise ValueError(f"Invalid email format: {email}")
        return email
    
    def _validate_path(self, path: str) -> str:
        """Validate file system path"""
        if not os.path.exists(path):
            self.warnings.append(f"Path does not exist: {path}")
        return path
    
    def _validate_secret_key(self, secret: str) -> bool:
        """Custom validator for secret keys"""
        # Check for common weak patterns
        weak_patterns = ['secret', 'password', '123456', 'admin', 'test']
        if any(pattern in secret.lower() for pattern in weak_patterns):
            return False
        
        # Check for sufficient entropy (basic check)
        if len(set(secret)) < len(secret) * 0.5:  # At least 50% unique characters
            return False
        
        return True
    
    def _perform_additional_validations(self, config: EnvironmentConfig):
        """Perform cross-field and business logic validations"""
        
        # Production environment checks
        if config.environment == 'production':
            if config.debug:
                self.warnings.append("Debug mode is enabled in production environment")
            
            if config.cors_origins == "*":
                self.warnings.append("CORS is configured to allow all origins in production")
            
            if not config.secret_key:
                raise ValueError("SECRET_KEY is required in production environment")
        
        # Port conflict checks
        ports_in_use = []
        if config.bff_port:
            ports_in_use.append(config.bff_port)
        if config.oms_port:
            ports_in_use.append(config.oms_port)
        if config.metrics_port:
            ports_in_use.append(config.metrics_port)
        
        if len(ports_in_use) != len(set(ports_in_use)):
            raise ValueError("Port conflicts detected: services cannot use the same port")
    
    def _log_configuration_summary(self, config: EnvironmentConfig):
        """Log configuration summary (masking sensitive values)"""
        summary = []
        summary.append(f"Environment: {config.environment}")
        summary.append(f"Debug mode: {config.debug}")
        summary.append(f"Log level: {config.log_level}")
        summary.append(f"BFF port: {config.bff_port}")
        summary.append(f"OMS URL: {config.oms_base_url}")
        
        logger.info("Configuration loaded: " + ", ".join(summary))


# Global instance
env_validator = EnvironmentValidator()


def validate_and_get_config() -> EnvironmentConfig:
    """Main entry point for environment validation"""
    return env_validator.validate_environment()


def get_config_value(key: str, default: Any = None) -> Any:
    """Get a configuration value with validation"""
    try:
        config = validate_and_get_config()
        return getattr(config, key.lower(), default)
    except Exception as e:
        logger.warning(f"Failed to get config value for {key}: {e}")
        return default