"""
API Routes
"""

from .history import router as history_router
from .audit import router as audit_router
from .reports import router as reports_router
from .health import router as health_router

__all__ = [
    "history_router",
    "audit_router", 
    "reports_router",
    "health_router",
]