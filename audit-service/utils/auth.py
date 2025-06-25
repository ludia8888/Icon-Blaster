"""
Authentication and Authorization Utilities
"""
from typing import Dict, List, Optional, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# HTTP Bearer 토큰 스키마
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Dict[str, Any]:
    """현재 사용자 정보 조회"""
    
    # TODO: 실제 JWT 토큰 검증 구현
    # 현재는 더미 구현
    
    token = credentials.credentials
    
    # 간단한 토큰 검증 (실제로는 JWT 라이브러리 사용)
    if not token or token == "invalid":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 더미 사용자 정보 반환
    return {
        "user_id": "user123",
        "email": "user@company.com",
        "name": "Test User",
        "roles": ["audit_user"],
        "permissions": [
            "audit:read",
            "history:read",
            "reports:read",
            "audit:export",
            "history:export"
        ],
        "accessible_branches": ["main", "develop"],
        "session_id": "session_abc123",
        "ip_address": "192.168.1.100"
    }


def require_permissions(
    user: Dict[str, Any],
    required_permissions: List[str],
    require_all: bool = False
) -> bool:
    """권한 확인"""
    
    user_permissions = user.get("permissions", [])
    user_roles = user.get("roles", [])
    
    # 관리자는 모든 권한 보유
    if "admin" in user_roles:
        return True
    
    # 권한 확인
    if require_all:
        # 모든 권한 필요
        has_permissions = all(perm in user_permissions for perm in required_permissions)
    else:
        # 하나 이상의 권한 필요
        has_permissions = any(perm in user_permissions for perm in required_permissions)
    
    if not has_permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required: {required_permissions}"
        )
    
    return True


def require_role(user: Dict[str, Any], required_role: str) -> bool:
    """역할 확인"""
    
    user_roles = user.get("roles", [])
    
    if required_role not in user_roles and "admin" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient role. Required: {required_role}"
        )
    
    return True


def get_user_context(user: Dict[str, Any]) -> Dict[str, Any]:
    """사용자 컨텍스트 생성"""
    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "name": user.get("name"),
        "roles": user.get("roles", []),
        "permissions": user.get("permissions", []),
        "accessible_branches": user.get("accessible_branches", []),
        "session_id": user.get("session_id"),
        "ip_address": user.get("ip_address"),
        "user_agent": user.get("user_agent")
    }


class PermissionChecker:
    """권한 확인 의존성"""
    
    def __init__(self, required_permissions: List[str], require_all: bool = False):
        self.required_permissions = required_permissions
        self.require_all = require_all
    
    def __call__(self, current_user: Dict[str, Any] = Depends(get_current_user)):
        require_permissions(current_user, self.required_permissions, self.require_all)
        return current_user


class RoleChecker:
    """역할 확인 의존성"""
    
    def __init__(self, required_role: str):
        self.required_role = required_role
    
    def __call__(self, current_user: Dict[str, Any] = Depends(get_current_user)):
        require_role(current_user, self.required_role)
        return current_user


# 공통 권한 체커들
audit_read_permission = PermissionChecker(["audit:read"])
audit_write_permission = PermissionChecker(["audit:write"])
audit_export_permission = PermissionChecker(["audit:export"])
history_read_permission = PermissionChecker(["history:read"])
history_export_permission = PermissionChecker(["history:export"])
reports_read_permission = PermissionChecker(["reports:read"])
reports_create_permission = PermissionChecker(["reports:create"])
admin_role = RoleChecker("admin")


def mask_sensitive_data(data: Dict[str, Any], fields_to_mask: List[str]) -> Dict[str, Any]:
    """민감한 데이터 마스킹"""
    masked_data = data.copy()
    
    for field in fields_to_mask:
        if field in masked_data:
            value = str(masked_data[field])
            if len(value) > 4:
                # 마지막 4자리 제외하고 마스킹
                masked_data[field] = "*" * (len(value) - 4) + value[-4:]
            else:
                # 전체 마스킹
                masked_data[field] = "*" * len(value)
    
    return masked_data


def get_data_classification_permissions(
    user: Dict[str, Any],
    data_classification: str
) -> bool:
    """데이터 분류별 접근 권한 확인"""
    
    user_roles = user.get("roles", [])
    user_permissions = user.get("permissions", [])
    
    # 관리자는 모든 데이터 접근 가능
    if "admin" in user_roles:
        return True
    
    # 데이터 분류별 권한 매핑
    classification_permissions = {
        "public": [],  # 모든 사용자 접근 가능
        "internal": ["data:internal"],
        "confidential": ["data:confidential"],
        "restricted": ["data:restricted"]
    }
    
    required_permissions = classification_permissions.get(data_classification, [])
    
    if not required_permissions:
        return True  # public 데이터
    
    return any(perm in user_permissions for perm in required_permissions)


def log_access_attempt(
    user: Dict[str, Any],
    resource_type: str,
    resource_id: str,
    action: str,
    success: bool,
    reason: Optional[str] = None
):
    """접근 시도 로깅"""
    from utils.logger import get_audit_logger
    
    audit_logger = get_audit_logger()
    
    audit_logger.log_user_action(
        user_id=user.get("user_id", "unknown"),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result="success" if success else "failure",
        ip_address=user.get("ip_address"),
        user_agent=user.get("user_agent"),
        session_id=user.get("session_id"),
        failure_reason=reason if not success else None
    )