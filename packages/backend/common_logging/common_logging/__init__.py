"""Common Logging Package

Unified logging utilities for user-service and oms-monolith.
Provides consistent JSON formatting, structured logging, and trace context.
"""

from .setup import setup_logging
from .formatter import JSONFormatter, StructuredFormatter
from .filters import TraceIDFilter, AuditFieldFilter, ServiceFilter

__version__ = "1.0.0"
__all__ = [
    "setup_logging",
    "JSONFormatter",
    "StructuredFormatter", 
    "TraceIDFilter",
    "AuditFieldFilter",
    "ServiceFilter",
]