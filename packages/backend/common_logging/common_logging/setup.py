"""Logging Setup

Unified logging configuration replacing user-service and oms-monolith
logging setup functions.
"""

import logging
import os
from typing import Optional, Dict, Any, List
from .formatter import create_formatter
from .filters import TraceIDFilter, ServiceFilter, AuditFieldFilter, SensitiveDataFilter


def setup_logging(
    service: str = "unknown",
    version: str = "1.0.0",
    level: str = "INFO",
    format_type: str = "json",
    environment: Optional[str] = None,
    enable_trace: bool = True,
    enable_audit: bool = False,
    mask_sensitive: bool = True,
    extra_fields: Optional[Dict[str, Any]] = None,
    handlers: Optional[List[logging.Handler]] = None
) -> logging.Logger:
    """Setup unified logging configuration.
    
    Args:
        service: Service name
        version: Service version
        level: Log level ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
        format_type: Format type ("json", "structured", "audit")
        environment: Environment name (defaults to ENVIRONMENT env var)
        enable_trace: Enable trace ID injection
        enable_audit: Enable audit-specific formatting
        mask_sensitive: Enable sensitive data masking
        extra_fields: Additional fields to include in logs
        handlers: Custom handlers (defaults to console handler)
    
    Returns:
        Configured root logger
    """
    # Get environment from env var if not provided
    if environment is None:
        environment = os.getenv("ENVIRONMENT", "unknown")
    
    # Get log level from env var if not explicitly set
    if level == "INFO":
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Get format type from env var if not explicitly set
    if format_type == "json":
        format_type = os.getenv("LOG_FORMAT", "json").lower()
    
    # Clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Set log level
    root_logger.setLevel(getattr(logging, level))
    
    # Create formatter
    formatter_kwargs = {
        "service": service,
        "version": version,
        "include_trace": enable_trace,
        "extra_fields": extra_fields or {}
    }
    
    if format_type == "audit":
        enable_audit = True
    
    formatter = create_formatter(format_type, **formatter_kwargs)
    
    # Create handlers
    if handlers is None:
        handlers = [logging.StreamHandler()]
    
    # Configure handlers
    for handler in handlers:
        handler.setFormatter(formatter)
        
        # Add filters
        if enable_trace:
            handler.addFilter(TraceIDFilter(auto_generate=True))
        
        handler.addFilter(ServiceFilter(service, version, environment))
        
        if enable_audit:
            handler.addFilter(AuditFieldFilter())
        
        if mask_sensitive:
            handler.addFilter(SensitiveDataFilter())
        
        root_logger.addHandler(handler)
    
    # Log setup completion
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "service": service,
            "version": version,
            "level": level,
            "format": format_type,
            "environment": environment,
            "trace_enabled": enable_trace,
            "audit_enabled": enable_audit,
            "sensitive_masking": mask_sensitive,
        }
    )
    
    return root_logger


def setup_file_logging(
    service: str,
    log_file: str,
    **kwargs
) -> logging.Logger:
    """Setup logging with file output.
    
    Args:
        service: Service name
        log_file: Path to log file
        **kwargs: Additional arguments for setup_logging
    
    Returns:
        Configured logger
    """
    # Create file handler
    file_handler = logging.FileHandler(log_file)
    
    # Setup logging with file handler
    return setup_logging(
        service=service,
        handlers=[file_handler],
        **kwargs
    )


def setup_rotating_file_logging(
    service: str,
    log_file: str,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    **kwargs
) -> logging.Logger:
    """Setup logging with rotating file output.
    
    Args:
        service: Service name
        log_file: Path to log file
        max_bytes: Maximum file size before rotation
        backup_count: Number of backup files to keep
        **kwargs: Additional arguments for setup_logging
    
    Returns:
        Configured logger
    """
    from logging.handlers import RotatingFileHandler
    
    # Create rotating file handler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count
    )
    
    # Setup logging with rotating file handler
    return setup_logging(
        service=service,
        handlers=[file_handler],
        **kwargs
    )


def setup_syslog_logging(
    service: str,
    address: str = "localhost",
    port: int = 514,
    facility: int = 16,  # LOG_LOCAL0
    **kwargs
) -> logging.Logger:
    """Setup logging with syslog output.
    
    Args:
        service: Service name
        address: Syslog server address
        port: Syslog server port
        facility: Syslog facility
        **kwargs: Additional arguments for setup_logging
    
    Returns:
        Configured logger
    """
    from logging.handlers import SysLogHandler
    
    # Create syslog handler
    syslog_handler = SysLogHandler(
        address=(address, port),
        facility=facility
    )
    
    # Setup logging with syslog handler
    return setup_logging(
        service=service,
        handlers=[syslog_handler],
        **kwargs
    )


def get_logger(name: str) -> logging.Logger:
    """Get logger instance.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def configure_third_party_loggers(level: str = "WARNING"):
    """Configure third-party library loggers.
    
    Args:
        level: Log level for third-party loggers
    """
    # Common third-party loggers to configure
    third_party_loggers = [
        "urllib3",
        "requests",
        "boto3",
        "botocore",
        "asyncio",
        "aiohttp",
        "sqlalchemy",
        "uvicorn",
        "fastapi",
        "starlette",
    ]
    
    for logger_name in third_party_loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level))


# Convenience functions for common configurations
def setup_audit_logging(service: str = "audit", **kwargs) -> logging.Logger:
    """Setup audit-specific logging configuration."""
    return setup_logging(
        service=service,
        format_type="audit",
        enable_audit=True,
        **kwargs
    )


def setup_development_logging(service: str, **kwargs) -> logging.Logger:
    """Setup development-friendly logging configuration."""
    return setup_logging(
        service=service,
        level="DEBUG",
        format_type="structured",
        environment="development",
        mask_sensitive=False,
        **kwargs
    )


def setup_production_logging(service: str, **kwargs) -> logging.Logger:
    """Setup production logging configuration."""
    return setup_logging(
        service=service,
        level="INFO",
        format_type="json",
        environment="production",
        mask_sensitive=True,
        **kwargs
    )