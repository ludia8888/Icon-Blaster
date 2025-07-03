"""
Logger Bridge - Connects existing logger usage to unified logger
Maintains backward compatibility while migrating to unified logger
"""

import warnings
import logging
from typing import Optional, Dict, Any, Union
from utils.unified_logger import (
    get_logger as unified_get_logger,
    get_structured_logger as unified_get_structured_logger,
    setup_logging,
    LogLevel,
    add_log_context
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

# Re-export original components
__all__ = [
    'get_logger',
    'get_structured_logger',
    'StructuredFormatter',
    'StructuredLoggerAdapter', 
    'LogLevel',
    'log_operation_start',
    'log_operation_end',
    'log_validation_result',
    'log_performance_metric',
    'configure_production_logging',
    'configure_development_logging'
]


def get_logger(
    name: Optional[str] = None,
    level: Union[str, LogLevel] = LogLevel.INFO,
    use_json: bool = None,
    service_name: str = "oms-monolith",
    version: str = "1.0.0"
):
    """
    Bridge function that redirects to unified logger
    Maintains the same interface as original logger.py
    """
    # Show deprecation warning on first use
    if not hasattr(get_logger, '_warning_shown'):
        warnings.warn(
            "utils.logger.get_logger is being migrated to utils.unified_logger.get_logger. "
            "Please update your imports.",
            DeprecationWarning,
            stacklevel=2
        )
        get_logger._warning_shown = True
    
    # Configure unified logger based on parameters
    import os
    if use_json is None:
        use_json = os.environ.get("LOG_FORMAT", "text").lower() == "json"
    
    # Setup unified logging if not already done
    level_str = str(level)
    if level_str.startswith('LogLevel.'):
        level_str = level_str.replace('LogLevel.', '')
    setup_logging(
        level=level_str,
        json_format=use_json,
        service_name=service_name,
        version=version
    )
    
    # Return unified logger
    return unified_get_logger(name or __name__)


def get_structured_logger(
    name: Optional[str] = None,
    context: Dict[str, Any] = None,
    **kwargs
):
    """
    Bridge function for structured logger
    Maps to unified structured logger
    """
    # Add context to unified logger
    if context:
        add_log_context(**context)
    
    # Get unified structured logger
    return unified_get_structured_logger(name or __name__)


# Auto-configuration based on environment
import os
if os.environ.get("ENVIRONMENT", "development").lower() in ["production", "prod", "staging"]:
    configure_production_logging()
else:
    configure_development_logging()