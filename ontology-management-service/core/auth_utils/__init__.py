"""
Auth Utils Module
This package exports the core authentication/authorization models and utilities.
"""
from core.auth.models import UserContext

def get_permission_checker():
    """Get permission checker utility"""
    # For now, return a simple lambda that always returns True
    # TODO: Implement proper permission checking logic
    return lambda user, permission: True

__all__ = ["UserContext", "get_permission_checker"]