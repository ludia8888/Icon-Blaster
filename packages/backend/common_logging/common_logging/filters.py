"""Logging Filters

Filters for adding trace context, service information,
and audit fields to log records.
"""

import logging
import uuid
import contextvars
from typing import Optional, Dict, Any


# Context variables for trace information
trace_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "trace_id", default=None
)
span_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "span_id", default=None
)
correlation_id_context: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


class TraceIDFilter(logging.Filter):
    """Filter to add trace ID, span ID, and correlation ID to log records."""
    
    def __init__(self, auto_generate: bool = True):
        super().__init__()
        self.auto_generate = auto_generate
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add trace information to log record."""
        # Get trace ID from context
        trace_id = trace_id_context.get()
        if not trace_id and self.auto_generate:
            trace_id = str(uuid.uuid4())
            trace_id_context.set(trace_id)
        
        # Get span ID from context
        span_id = span_id_context.get()
        if not span_id and self.auto_generate:
            span_id = str(uuid.uuid4())[:8]
            span_id_context.set(span_id)
        
        # Get correlation ID from context
        correlation_id = correlation_id_context.get()
        
        # Add to record
        record.trace_id = trace_id
        record.span_id = span_id
        record.correlation_id = correlation_id
        
        return True


class ServiceFilter(logging.Filter):
    """Filter to add service information to log records."""
    
    def __init__(self, service: str, version: str = "1.0.0", environment: str = "unknown"):
        super().__init__()
        self.service = service
        self.version = version
        self.environment = environment
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add service information to log record."""
        record.service = self.service
        record.version = self.version
        record.environment = self.environment
        return True


class AuditFieldFilter(logging.Filter):
    """Filter to add audit-specific fields to log records."""
    
    def __init__(self, default_fields: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.default_fields = default_fields or {}
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add audit fields to log record."""
        # Add default audit fields
        for key, value in self.default_fields.items():
            if not hasattr(record, key):
                setattr(record, key, value)
        
        # Ensure required audit fields exist
        audit_fields = [
            "event_type", "user_id", "resource_id", "action", 
            "result", "ip_address", "user_agent"
        ]
        
        for field in audit_fields:
            if not hasattr(record, field):
                setattr(record, field, None)
        
        return True


class SensitiveDataFilter(logging.Filter):
    """Filter to remove or mask sensitive data from log records."""
    
    def __init__(self, sensitive_fields: Optional[list] = None):
        super().__init__()
        self.sensitive_fields = sensitive_fields or [
            "password", "token", "secret", "key", "authorization",
            "cookie", "session", "credit_card", "ssn", "email"
        ]
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Mask sensitive data in log record."""
        # Mask sensitive data in message
        message = record.getMessage()
        for field in self.sensitive_fields:
            if field.lower() in message.lower():
                # Simple masking - replace with asterisks
                import re
                pattern = rf"({field}[=:\s]+)([^\s,}}]+)"
                message = re.sub(pattern, r"\1****", message, flags=re.IGNORECASE)
        
        # Update record message
        record.msg = message
        record.args = ()
        
        # Mask sensitive data in record attributes
        for attr_name in dir(record):
            if not attr_name.startswith("_"):
                attr_value = getattr(record, attr_name)
                if isinstance(attr_value, str):
                    for field in self.sensitive_fields:
                        if field.lower() in attr_name.lower():
                            setattr(record, attr_name, "****")
                            break
        
        return True


class PerformanceFilter(logging.Filter):
    """Filter to add performance metrics to log records."""
    
    def __init__(self, track_memory: bool = False):
        super().__init__()
        self.track_memory = track_memory
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add performance metrics to log record."""
        import time
        import threading
        
        # Add thread information
        record.thread_name = threading.current_thread().name
        record.thread_id = threading.get_ident()
        
        # Add timing information
        if not hasattr(record, "start_time"):
            record.start_time = time.time()
        
        # Add memory information if requested
        if self.track_memory:
            try:
                import psutil
                import os
                
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                record.memory_rss = memory_info.rss
                record.memory_vms = memory_info.vms
                record.memory_percent = process.memory_percent()
            except ImportError:
                pass
        
        return True


# Context management functions
def set_trace_id(trace_id: str):
    """Set trace ID in context."""
    trace_id_context.set(trace_id)


def set_span_id(span_id: str):
    """Set span ID in context."""
    span_id_context.set(span_id)


def set_correlation_id(correlation_id: str):
    """Set correlation ID in context."""
    correlation_id_context.set(correlation_id)


def get_trace_id() -> Optional[str]:
    """Get current trace ID from context."""
    return trace_id_context.get()


def get_span_id() -> Optional[str]:
    """Get current span ID from context."""
    return span_id_context.get()


def get_correlation_id() -> Optional[str]:
    """Get current correlation ID from context."""
    return correlation_id_context.get()


def clear_trace_context():
    """Clear all trace context variables."""
    trace_id_context.set(None)
    span_id_context.set(None)
    correlation_id_context.set(None)