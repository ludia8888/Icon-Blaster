"""
Enhanced Authentication Middleware
User Service와 연동하여 JWT 토큰 검증 및 사용자 컨텍스트 주입
"""
from typing import Optional, Callable
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.auth import get_permission_checker, UserContext
from core.integrations.user_service_client import validate_jwt_token, UserServiceError
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
            "/redoc",
            "/"
        ]
        self.permission_checker = get_permission_checker()
        # 토큰 캐시 (실제 환경에서는 Redis 사용 권장)
        self._token_cache = {}
        self.cache_ttl = 300  # 5분
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 공개 경로는 인증 스킵
        if any(request.url.path.startswith(path) for path in self.public_paths):
            return await call_next(request)
        
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
                # User Service를 통한 토큰 검증
                user = await validate_jwt_token(token)
                self._cache_user(token, user)
                logger.info(f"Authenticated user {user.username} via User Service for {request.url.path}")
            
            # 사용자 컨텍스트를 request.state에 저장
            request.state.user = user
            
        except UserServiceError as e:
            logger.warning(f"User Service authentication failed for {request.url.path}: {e}")
            return Response(
                content=f'{{"detail": "Authentication failed: {str(e)}"}}',
                status_code=status.HTTP_401_UNAUTHORIZED,
                headers={"WWW-Authenticate": "Bearer"}
            )
        except Exception as e:
            logger.error(f"Unexpected authentication error for {request.url.path}: {e}")
            return Response(
                content='{"detail": "Internal authentication error"}',
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
    if not hasattr(request.state, "user"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return request.state.user


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