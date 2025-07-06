"""
Common Logging Setup Module
Provides centralized logging configuration
"""

import logging
import os
from typing import Optional, Dict, Any

from . import JSONFormatter, StructuredFormatter, ServiceFilter


# Global logger cache
_loggers: Dict[str, logging.Logger] = {}
_setup_done = False


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    Get a logger instance with consistent configuration
    
    Args:
        name: Logger name (defaults to caller's module)
    
    Returns:
        Configured logger instance
    """
    if name is None:
        import inspect
        frame = inspect.currentframe().f_back
        name = frame.f_globals.get('__name__', 'unknown')
    
    if name in _loggers:
        return _loggers[name]
    
    # Ensure basic setup is done
    if not _setup_done:
        setup_logging()
    
    logger = logging.getLogger(name)
    _loggers[name] = logger
    return logger


def setup_logging(
    service: str = "oms",
    version: str = "1.0.0", 
    level: str = "INFO",
    format_type: str = "structured",
    extra_fields: Optional[Dict[str, Any]] = None
):
    """
    Setup global logging configuration
    
    Args:
        service: Service name
        version: Service version
        level: Logging level
        format_type: 'json' or 'structured'
        extra_fields: Additional fields to include
    """
    global _setup_done
    
    # Get log level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler()
    handler.setLevel(numeric_level)
    
    # Set formatter
    if format_type.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = StructuredFormatter()
    
    handler.setFormatter(formatter)
    
    # Add filters
    handler.addFilter(ServiceFilter(service, version))
    
    # Add handler to root logger
    root_logger.addHandler(handler)
    
    _setup_done = True


def setup_development_logging(service: str = "oms", level: str = "DEBUG"):
    """Setup development logging (structured text)"""
    setup_logging(
        service=service,
        level=level,
        format_type="structured"
    )


def setup_production_logging(service: str = "oms", level: str = "INFO"):
    """Setup production logging (JSON)"""
    setup_logging(
        service=service,
        level=level,
        format_type="json"
    )


# Auto-setup based on environment
def _auto_setup():
    """Automatically setup logging based on environment"""
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    if env in ["production", "prod", "staging"]:
        setup_production_logging()
    else:
        setup_development_logging()


# Perform auto-setup on import
_auto_setup()