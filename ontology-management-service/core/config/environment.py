"""
Environment Configuration and Guards
Ensures proper environment-based behavior
"""
import os
from enum import Enum
from typing import Optional

from common_logging.setup import get_logger

logger = get_logger(__name__)


class Environment(str, Enum):
    """Application environments"""
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TEST = "test"
    LOCAL = "local"


class EnvironmentConfig:
    """Environment configuration and validation"""
    
    def __init__(self):
        self._env = os.getenv("ENV", "development").lower()
        self._validate_environment()
    
    def _validate_environment(self):
        """Validate environment value"""
        valid_envs = [e.value for e in Environment]
        if self._env not in valid_envs:
            logger.warning(
                f"Unknown environment '{self._env}', defaulting to 'development'. "
                f"Valid values: {valid_envs}"
            )
            self._env = Environment.DEVELOPMENT.value
    
    @property
    def current(self) -> str:
        """Get current environment"""
        return self._env
    
    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self._env == Environment.PRODUCTION.value
    
    @property
    def is_staging(self) -> bool:
        """Check if running in staging"""
        return self._env == Environment.STAGING.value
    
    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self._env in [Environment.DEVELOPMENT.value, Environment.LOCAL.value]
    
    @property
    def is_test(self) -> bool:
        """Check if running in test environment"""
        return self._env == Environment.TEST.value
    
    @property
    def allows_mock_auth(self) -> bool:
        """Check if mock authentication is allowed"""
        return not self.is_production and not self.is_staging
    
    @property
    def allows_test_routes(self) -> bool:
        """Check if test routes should be registered"""
        return not self.is_production
    
    def require_production(self):
        """Raise error if not in production"""
        if not self.is_production:
            raise RuntimeError(
                f"This operation requires production environment, current: {self._env}"
            )
    
    def require_non_production(self):
        """Raise error if in production"""
        if self.is_production:
            raise RuntimeError(
                "This operation is not allowed in production environment"
            )
    
    def log_environment(self):
        """Log current environment configuration"""
        logger.info(f"Environment: {self._env}")
        logger.info(f"Mock auth allowed: {self.allows_mock_auth}")
        logger.info(f"Test routes allowed: {self.allows_test_routes}")
        
        if self.is_production:
            logger.warning("Running in PRODUCTION mode - all test features disabled")
        elif self.is_staging:
            logger.info("Running in STAGING mode - limited test features")
        else:
            logger.info(f"Running in {self._env.upper()} mode - test features enabled")


# Global instance
env_config = EnvironmentConfig()


def get_environment() -> EnvironmentConfig:
    """Get environment configuration instance"""
    return env_config


def ensure_test_environment(operation: str):
    """
    Decorator to ensure operation only runs in test environments
    
    Args:
        operation: Description of the operation
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            if env_config.is_production or env_config.is_staging:
                raise RuntimeError(
                    f"Operation '{operation}' is not allowed in {env_config.current} environment"
                )
            return func(*args, **kwargs)
        return wrapper
    return decorator