"""
Core Audit Module - Read-Only Adapter
"""

# Legacy imports (deprecated)
from .audit_service import AuditService, get_audit_service

# Current imports
from shared.audit_client import AuditServiceClient, AuditEvent, AuditEventBatch

__all__ = [
    # Deprecated
    'AuditService', 
    'get_audit_service',
    
    # Current
    'AuditServiceClient',
    'AuditEvent', 
    'AuditEventBatch'
]

# Deprecation warning
import warnings
warnings.warn(
    "core.audit module is deprecated. Use shared.audit_client directly for new code.",
    DeprecationWarning,
    stacklevel=2
)