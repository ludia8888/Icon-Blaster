"""
Common Logging Module for OMS
Provides structured logging across all services
"""

import logging
import json
import os
from typing import Optional, Dict, Any, Union
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
            
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
            
        return json.dumps(log_data)


class StructuredFormatter(logging.Formatter):
    """Structured text formatter"""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


class TraceIDFilter(logging.Filter):
    """Add trace ID to log records"""
    
    def filter(self, record):
        record.trace_id = getattr(record, 'trace_id', 'no-trace')
        return True


class AuditFieldFilter(logging.Filter):
    """Add audit fields to log records"""
    
    def filter(self, record):
        record.audit_user = getattr(record, 'audit_user', 'system')
        record.audit_action = getattr(record, 'audit_action', 'unknown')
        return True


class ServiceFilter(logging.Filter):
    """Add service info to log records"""
    
    def __init__(self, service_name: str = "oms", version: str = "1.0.0"):
        super().__init__()
        self.service_name = service_name
        self.version = version
    
    def filter(self, record):
        record.service = self.service_name
        record.version = self.version
        return True


__all__ = [
    'JSONFormatter',
    'StructuredFormatter', 
    'TraceIDFilter',
    'AuditFieldFilter',
    'ServiceFilter'
]