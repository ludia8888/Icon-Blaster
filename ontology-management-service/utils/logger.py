"""
Logger Bridge - Connects existing logger usage to common_logging
Maintains backward compatibility while migrating to common_logging
"""

import warnings
import logging
from typing import Optional, Dict, Any, Union
from common_logging.setup import (
    get_logger as common_get_logger,
    setup_logging,
    setup_development_logging,
    setup_production_logging
)
from common_logging import (
    JSONFormatter,
    StructuredFormatter,
    TraceIDFilter,
    AuditFieldFilter,
    ServiceFilter
)

# Import original components for backward compatibility
try:
    from utils.logger_original import (
        StructuredFormatter,
        StructuredLoggerAdapter,
        log_operation_start,
        log_operation_end,
        log_validation_result,
        log_performance_metric,
        configure_production_logging,
        configure_development_logging
    )
except ImportError:
    # Fallback implementations if original logger is not available
    StructuredFormatter = None
    StructuredLoggerAdapter = None
    log_operation_start = lambda *args, **kwargs: None
    log_operation_end = lambda *args, **kwargs: None
    log_validation_result = lambda *args, **kwargs: None
    log_performance_metric = lambda *args, **kwargs: None
    configure_production_logging = lambda *args, **kwargs: None
    configure_development_logging = lambda *args, **kwargs: None

# Re-export original components and common_logging components
__all__ = [
    'get_logger',
    'get_structured_logger',
    'setup_logging',
    'setup_development_logging',
    'setup_production_logging',
    'JSONFormatter',
    'StructuredFormatter',
    'TraceIDFilter',
    'AuditFieldFilter',
    'ServiceFilter',
    'StructuredLoggerAdapter',  # backward compatibility
    'log_operation_start',
    'log_operation_end',
    'log_validation_result',
    'log_performance_metric',
    'configure_production_logging',
    'configure_development_logging'
]


def get_logger(
    name: Optional[str] = None,
    level: str = "INFO",
    use_json: bool = None,
    service_name: str = "oms-monolith",
    version: str = "1.0.0"
):
    """
    Bridge function that redirects to common_logging
    Maintains the same interface as original logger.py
    """
    # Show deprecation warning on first use
    if not hasattr(get_logger, '_warning_shown'):
        warnings.warn(
            "utils.logger.get_logger is being migrated to common_logging.setup.get_logger. "
            "Please update your imports to use common_logging directly.",
            DeprecationWarning,
            stacklevel=2
        )
        get_logger._warning_shown = True
    
    # Configure common_logging based on parameters
    import os
    if use_json is None:
        use_json = os.environ.get("LOG_FORMAT", "text").lower() == "json"
    
    # Setup common_logging if not already done
    level_str = str(level)
    if level_str.startswith('LogLevel.'):
        level_str = level_str.replace('LogLevel.', '')
    
    format_type = "json" if use_json else "structured"
    setup_logging(
        service=service_name,
        version=version,
        level=level_str,
        format_type=format_type
    )
    
    # Return common_logging logger
    return common_get_logger(name or __name__)


def get_structured_logger(
    name: Optional[str] = None,
    context: Dict[str, Any] = None,
    **kwargs
):
    """
    Bridge function for structured logger
    Maps to common_logging structured logger
    """
    # Setup common_logging with extra fields from context
    if context:
        setup_logging(
            service="oms-monolith", 
            extra_fields=context,
            **kwargs
        )
    
    # Get common_logging logger
    return common_get_logger(name or __name__)


# Auto-configuration based on environment
import os
if os.environ.get("ENVIRONMENT", "development").lower() in ["production", "prod", "staging"]:
    try:
        setup_production_logging(service="oms-monolith")
    except Exception:
        # Fallback to original if common_logging not available
        configure_production_logging()
else:
    try:
        setup_development_logging(service="oms-monolith")
    except Exception:
        # Fallback to original if common_logging not available
        configure_development_logging()