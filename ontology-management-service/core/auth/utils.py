"""
Core Authentication/Authorization Utilities
"""
from models.permissions import get_permission_checker as _get_permission_checker, PermissionChecker

def get_permission_checker() -> PermissionChecker:
    """Get the global permission checker instance"""
    return _get_permission_checker() 