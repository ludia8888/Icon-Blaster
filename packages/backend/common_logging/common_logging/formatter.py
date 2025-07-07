"""Logging Formatters

Unified JSON and structured logging formatters replacing
user-service pythonjsonlogger and oms-monolith custom formatters.
"""

import json
import logging
import traceback
from datetime import datetime
from typing import Dict, Any, Optional


class JSONFormatter(logging.Formatter):
    """JSON log formatter with consistent field structure."""
    
    def __init__(
        self,
        service: str = "unknown",
        version: str = "1.0.0",
        include_trace: bool = True,
        extra_fields: Optional[Dict[str, Any]] = None
    ):
        super().__init__()
        self.service = service
        self.version = version
        self.include_trace = include_trace
        self.extra_fields = extra_fields or {}
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_obj = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service,
            "version": self.version,
        }
        
        # Add trace information
        if self.include_trace:
            log_obj.update({
                "trace_id": getattr(record, "trace_id", None),
                "span_id": getattr(record, "span_id", None),
                "correlation_id": getattr(record, "correlation_id", None),
            })
        
        # Add exception info
        if record.exc_info:
            log_obj["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "lineno", "funcName", "created",
                "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "exc_info", "exc_text",
                "stack_info", "getMessage"
            }:
                log_obj[key] = value
        
        # Add configured extra fields
        log_obj.update(self.extra_fields)
        
        return json.dumps(log_obj, separators=(",", ":"), ensure_ascii=False)


class StructuredFormatter(logging.Formatter):
    """Structured text formatter for development and debugging."""
    
    def __init__(
        self,
        service: str = "unknown",
        include_trace: bool = True,
        colored: bool = False
    ):
        super().__init__()
        self.service = service
        self.include_trace = include_trace
        self.colored = colored
        
        # Color codes
        self.colors = {
            "DEBUG": "\033[36m",    # Cyan
            "INFO": "\033[32m",     # Green
            "WARNING": "\033[33m",  # Yellow
            "ERROR": "\033[31m",    # Red
            "CRITICAL": "\033[35m", # Magenta
            "RESET": "\033[0m"
        }
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured text."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        
        # Build base message
        parts = [
            timestamp,
            f"[{self.service}]",
            f"[{record.levelname}]",
            f"[{record.name}]",
            record.getMessage()
        ]
        
        # Add trace information
        if self.include_trace:
            trace_id = getattr(record, "trace_id", None)
            if trace_id:
                parts.insert(-1, f"[trace:{trace_id[:8]}]")
        
        message = " ".join(parts)
        
        # Add color if enabled
        if self.colored:
            color = self.colors.get(record.levelname, "")
            reset = self.colors["RESET"]
            message = f"{color}{message}{reset}"
        
        # Add exception info
        if record.exc_info:
            message += "\n" + traceback.format_exception(*record.exc_info)[-1]
        
        return message


class AuditFormatter(JSONFormatter):
    """Specialized formatter for audit logs."""
    
    def __init__(self, service: str = "audit", **kwargs):
        super().__init__(service=service, **kwargs)
    
    def format(self, record: logging.LogRecord) -> str:
        """Format audit log record with additional audit fields."""
        # Get base JSON formatting
        log_data = json.loads(super().format(record))
        
        # Add audit-specific fields
        log_data["audit"] = {
            "event_type": getattr(record, "event_type", "unknown"),
            "user_id": getattr(record, "user_id", None),
            "resource_id": getattr(record, "resource_id", None),
            "action": getattr(record, "action", None),
            "result": getattr(record, "result", None),
            "ip_address": getattr(record, "ip_address", None),
            "user_agent": getattr(record, "user_agent", None),
        }
        
        return json.dumps(log_data, separators=(",", ":"), ensure_ascii=False)


def create_formatter(
    format_type: str = "json",
    service: str = "unknown",
    version: str = "1.0.0",
    **kwargs
) -> logging.Formatter:
    """Create appropriate formatter based on type.
    
    Args:
        format_type: "json", "structured", or "audit"
        service: Service name
        version: Service version
        **kwargs: Additional formatter arguments
    
    Returns:
        Configured formatter instance
    """
    if format_type == "json":
        return JSONFormatter(service=service, version=version, **kwargs)
    elif format_type == "structured":
        # Filter kwargs for StructuredFormatter
        structured_kwargs = {k: v for k, v in kwargs.items() 
                           if k in ['include_trace', 'colored']}
        return StructuredFormatter(service=service, **structured_kwargs)
    elif format_type == "audit":
        return AuditFormatter(service=service, version=version, **kwargs)
    else:
        raise ValueError(f"Unknown format type: {format_type}")