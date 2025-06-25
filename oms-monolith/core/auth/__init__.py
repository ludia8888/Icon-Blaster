"""
Auth Module - Minimal Resource Permission Checking
실제 인증/인가는 외부 IdP 서비스에 위임
"""
from .resource_permission_checker import (
    ResourcePermissionChecker,
    UserContext,
    ResourceType,
    Action,
    get_permission_checker,
    check_permission
)

__all__ = [
    'ResourcePermissionChecker',
    'UserContext', 
    'ResourceType',
    'Action',
    'get_permission_checker',
    'check_permission'
]