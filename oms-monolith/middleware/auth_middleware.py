"""
Enhanced Authentication Middleware
User Service와 연동하여 JWT 토큰 검증 및 사용자 컨텍스트 주입

DESIGN INTENT - AUTHENTICATION LAYER:
This middleware handles ONLY authentication (who you are), NOT authorization (what you can do).
It operates as the first security layer in the middleware stack.

SEPARATION OF CONCERNS:
1. AuthMiddleware (THIS): Validates identity, creates user context
2. RBACMiddleware: Checks role-based permissions
3. AuditMiddleware: Logs security-relevant actions

WHY SEPARATE AUTH FROM RBAC:
- Single Responsibility: Auth = Identity, RBAC = Permissions
- Flexibility: Can swap auth methods (JWT, OAuth, SAML) without touching permissions
- Performance: Skip RBAC checks for public endpoints after auth
- Testing: Test authentication and authorization independently
- Compliance: Different audit requirements for auth vs access

MIDDLEWARE EXECUTION ORDER:
1. AuthMiddleware → Validates token, sets request.state.user
2. RBACMiddleware → Reads request.state.user, checks permissions
3. AuditMiddleware → Logs the authenticated action

ARCHITECTURE BENEFITS:
- Clean separation allows different caching strategies per layer
- Auth tokens can be cached longer than permission checks
- Failed auth stops the request early (fail-fast)
- Each middleware can be toggled on/off independently

USE THIS FOR:
- JWT token validation
- Session management
- User context injection
- Public path handling

NOT FOR:
- Permission checks (use RBACMiddleware)
- Access control lists (use RBACMiddleware)
- Audit logging (use AuditMiddleware)

Related modules:
- middleware/rbac_middleware.py: Role-based access control
- middleware/audit_middleware.py: Security audit logging
- core/auth/unified_auth.py: Core authentication logic
"""
import os
from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.auth_utils import get_permission_checker, UserContext
from core.integrations.user_service_client import validate_jwt_token, UserServiceError
from core.iam.iam_integration import get_iam_integration
from utils.logger import get_logger

logger = get_logger(__name__)

# HTTP Bearer 인증 스키마
security = HTTPBearer(auto_error=False)


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Enhanced 인증 미들웨어
    - User Service를 통한 JWT 토큰 검증
    - 사용자 컨텍스트를 request.state에 저장
    - 공개 경로는 인증 스킵
    - 토큰 캐싱으로 성능 최적화
    """
    
    def __init__(self, app, public_paths: Optional[list] = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/health",
            "/metrics", 
            "/docs",
            "/openapi.json",
            "/redoc"
        ]
        self.permission_checker = get_permission_checker()
        # 토큰 캐시 (실제 환경에서는 Redis 사용 권장)
        self._token_cache = {}
        self.cache_ttl = 300  # 5분
        
        # IAM integration for enhanced JWT validation
        self.iam_integration = get_iam_integration()
        self.use_enhanced_validation = os.getenv("USE_IAM_VALIDATION", "false").lower() == "true"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 공개 경로는 인증 스킵
        # Check exact match for root path, startswith for others
        if request.url.path == "/" or any(request.url.path.startswith(path) for path in self.public_paths):
            return await call_next(request)
        
        logger.debug(f"AuthMiddleware processing {request.url.path}")
        
        # Authorization 헤더 확인
        authorization = request.headers.get("Authorization")
        if not authorization:
            logger.debug(f"No authorization header for {request.url.path}")
            return Response(
                content='{"detail": "Authorization header missing"}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        # Bearer 토큰 추출
        if not authorization.startswith("Bearer "):
            logger.debug(f"Invalid authorization format for {request.url.path}")
            return Response(
                content='{"detail": "Invalid authorization format"}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        token = authorization.split(" ")[1]
        
        try:
            # 캐시 확인
            cached_user = self._get_cached_user(token)
            if cached_user:
                user = cached_user
                logger.debug(f"Using cached user {user.username} for {request.url.path}")
            else:
                # Choose validation method based on configuration
                if self.use_enhanced_validation:
                    # Enhanced IAM validation with scope support
                    user = await self.iam_integration.validate_jwt_enhanced(token)
                    logger.info(f"Authenticated user {user.username} via IAM Service (with scopes) for {request.url.path}")
                else:
                    # Standard User Service validation
                    user = await validate_jwt_token(token)
                    logger.info(f"Authenticated user {user.username} via User Service for {request.url.path}")
                
                self._cache_user(token, user)
            
            # 사용자 컨텍스트를 request.state에 저장
            logger.debug(f"About to set user in request.state: {user}")
            request.state.user = user
            logger.debug(f"User {user.username} set in request.state for {request.url.path}")
            logger.debug(f"Verify - request.state.user is now: {getattr(request.state, 'user', 'NOT SET')}")
            
        except UserServiceError as e:
            logger.warning(f"User Service authentication failed for {request.url.path}: {e}")
            return Response(
                content=f'{{"detail": "Authentication failed: {str(e)}"}}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"}
            )
        except Exception as e:
            logger.error(f"Unexpected authentication error for {request.url.path}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return Response(
                content=f'{{"detail": "Internal authentication error: {str(e)}"}}',
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # 다음 미들웨어/핸들러 호출
        response = await call_next(request)
        return response
    
    def _get_cached_user(self, token: str) -> Optional[UserContext]:
        """캐시에서 사용자 정보 조회"""
        import time
        cached_data = self._token_cache.get(token)
        if cached_data:
            user_context, timestamp = cached_data
            if time.time() - timestamp < self.cache_ttl:
                return user_context
            else:
                # 캐시 만료
                del self._token_cache[token]
        return None
    
    def _cache_user(self, token: str, user_context: UserContext):
        """사용자 정보 캐시 저장"""
        import time
        self._token_cache[token] = (user_context, time.time())
        
        # 캐시 크기 제한 (간단한 LRU 구현)
        if len(self._token_cache) > 1000:
            # 가장 오래된 항목들 제거
            sorted_items = sorted(
                self._token_cache.items(), 
                key=lambda x: x[1][1]
            )
            for token_to_remove, _ in sorted_items[:100]:
                del self._token_cache[token_to_remove]


def get_current_user(request: Request) -> UserContext:
    """
    현재 요청의 사용자 정보 반환
    FastAPI 의존성으로 사용
    """
    # Get user context from request state
    if hasattr(request.state, 'user_context') and request.state.user_context:
        return request.state.user_context
    
    # If not in state, this is an error - auth middleware should have set it
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required"
    )


async def require_permission(
    request: Request,
    resource_type: str,
    resource_id: str,
    action: str
) -> UserContext:
    """
    특정 권한이 필요한 엔드포인트용 의존성
    
    Usage:
        @app.get("/schemas/{schema_id}")
        async def get_schema(
            schema_id: str,
            user: UserContext = Depends(
                lambda req: require_permission(req, "schema", schema_id, "read")
            )
        ):
            ...
    """
    user = get_current_user(request)
    
    checker = get_permission_checker()
    if not checker.check_permission(user, resource_type, resource_id, action):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {action} on {resource_type}:{resource_id}"
        )
    
    return user