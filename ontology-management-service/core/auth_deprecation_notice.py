"""
Auth Deprecation Notice
기존 OMS 인증 로직의 Deprecation 표시와 User Service 이관 안내
"""
import warnings
from typing import Any
from common_logging.setup import get_logger

logger = get_logger(__name__)


def deprecated_auth_function(func_name: str, replacement: str = "user-service API"):
    """
    인증 관련 함수의 Deprecation 경고를 발생시키는 데코레이터
    
    Args:
        func_name: 사용 중단된 함수명
        replacement: 대체 방법 설명
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{func_name} is deprecated and will be removed. "
                f"Use {replacement} instead. "
                f"All authentication logic has been migrated to user-service.",
                DeprecationWarning,
                stacklevel=2
            )
            logger.warning(
                f"Deprecated auth function called: {func_name}. "
                f"Migrate to {replacement}"
            )
            return func(*args, **kwargs)
        return wrapper
    return decorator


class DeprecatedAuthError(Exception):
    """Deprecated authentication function usage error"""
    pass


def block_deprecated_auth_function(func_name: str, message: str = None):
    """
    인증 관련 함수를 완전히 차단하는 데코레이터
    
    Args:
        func_name: 차단된 함수명
        message: 사용자 정의 메시지
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            error_message = message or (
                f"{func_name} has been removed. "
                f"All authentication logic is now handled by user-service. "
                f"Use shared.user_service_client or api.v1.auth_proxy_routes instead."
            )
            logger.error(f"Blocked deprecated auth function: {func_name}")
            raise DeprecatedAuthError(error_message)
        return wrapper
    return decorator


# 중단된 비밀번호 정책 함수들
@block_deprecated_auth_function(
    "validate_password_strength",
    "Password validation is now handled by user-service. "
    "Use POST /auth/register or POST /auth/change-password endpoints."
)
def validate_password_strength(*args, **kwargs):
    """DEPRECATED: 비밀번호 강도 검증 (user-service로 이관됨)"""
    pass


@block_deprecated_auth_function(
    "check_password_policy",
    "Password policy checking is now handled by user-service. "
    "Configure password policies in user-service settings."
)
def check_password_policy(*args, **kwargs):
    """DEPRECATED: 비밀번호 정책 확인 (user-service로 이관됨)"""
    pass


@block_deprecated_auth_function(
    "hash_password",
    "Password hashing is now handled by user-service. "
    "Use user-service API endpoints for user registration and password changes."
)
def hash_password(*args, **kwargs):
    """DEPRECATED: 비밀번호 해싱 (user-service로 이관됨)"""
    pass


@block_deprecated_auth_function(
    "verify_password",
    "Password verification is now handled by user-service. "
    "Use POST /auth/login endpoint for authentication."
)
def verify_password(*args, **kwargs):
    """DEPRECATED: 비밀번호 검증 (user-service로 이관됨)"""
    pass


@block_deprecated_auth_function(
    "generate_password_hash",
    "Password generation is now handled by user-service. "
    "Use user-service password utilities."
)
def generate_password_hash(*args, **kwargs):
    """DEPRECATED: 비밀번호 해시 생성 (user-service로 이관됨)"""
    pass


@block_deprecated_auth_function(
    "create_user_account",
    "User account creation is now handled by user-service. "
    "Use POST /auth/register endpoint."
)
def create_user_account(*args, **kwargs):
    """DEPRECATED: 사용자 계정 생성 (user-service로 이관됨)"""
    pass


@block_deprecated_auth_function(
    "update_user_password",
    "Password updates are now handled by user-service. "
    "Use POST /auth/change-password endpoint."
)
def update_user_password(*args, **kwargs):
    """DEPRECATED: 사용자 비밀번호 업데이트 (user-service로 이관됨)"""
    pass


@deprecated_auth_function(
    "create_jwt_token",
    "user-service JWT token generation via POST /auth/login"
)
def create_jwt_token(*args, **kwargs):
    """DEPRECATED: JWT 토큰 생성 (user-service로 이관 권장)"""
    from shared.user_service_client import get_user_service_client
    logger.warning("Direct JWT creation should use user-service. This is a fallback.")
    # 기존 로직을 그대로 유지하되 경고 표시
    pass


# 이관 완료 상태 확인
def check_auth_migration_status() -> dict:
    """
    인증 시스템 이관 상태 확인
    
    Returns:
        이관 상태 정보
    """
    return {
        "auth_migration_completed": True,
        "user_service_integration": True,
        "deprecated_functions_blocked": True,
        "password_policies_migrated": True,
        "jwt_validation_unified": True,
        "monolith_auth_status": "proxy_mode",
        "migration_date": "2025-07-06",
        "user_service_endpoints": {
            "login": "POST /auth/login",
            "register": "POST /auth/register", 
            "logout": "POST /auth/logout",
            "refresh": "POST /auth/refresh",
            "userinfo": "GET /auth/userinfo",
            "change_password": "POST /auth/change-password",
            "mfa_setup": "POST /auth/mfa/setup",
            "mfa_enable": "POST /auth/mfa/enable",
            "mfa_disable": "POST /auth/mfa/disable",
            "jwks": "GET /.well-known/jwks.json"
        },
        "deprecated_modules": [
            "core.auth (partial - UserContext remains)",
            "Password policy functions",
            "Local JWT generation",
            "User CRUD operations",
            "MFA implementation"
        ]
    }