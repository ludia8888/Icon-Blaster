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
from typing import Optional, Callable, Dict, Any
from fastapi import Request, HTTPException, status, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import redis.asyncio as redis
import json
import httpx
import inspect

from core.auth import UserContext
from bootstrap.config import get_config
from middleware.circuit_breaker import CircuitBreakerGroup, CircuitBreakerError
from common_logging.setup import get_logger

logger = get_logger(__name__)

class AuthMiddleware(BaseHTTPMiddleware):
    """
    Enhanced 인증 미들웨어
    - User Service를 통한 JWT 토큰 검증
    - 사용자 컨텍스트를 request.state에 저장
    - 공개 경로는 인증 스킵
    - 토큰 캐싱으로 성능 최적화
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        config = get_config()
        self.user_service_url = config.user_service.url
        self.client = httpx.AsyncClient(timeout=5.0)
        self.public_paths = [
            "/health", "/metrics", "/docs", "/openapi.json", "/redoc",
            "/api/v1/health", "/api/v1/health/live", "/api/v1/health/ready"
        ]
        self.cache_ttl = 300
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path == "/" or any(request.url.path.startswith(path) for path in self.public_paths):
            return await call_next(request)

        authorization = request.headers.get("Authorization")
        if not authorization or not authorization.startswith("Bearer "):
            return Response('{"detail": "Unauthorized"}', status_code=401, headers={"WWW-Authenticate": "Bearer"})
        
        token = authorization.split(" ")[1]

        try:
            redis_provider = request.app.state.redis_client
            if inspect.iscoroutine(redis_provider):
                redis_client = await redis_provider
            else:
                redis_client = redis_provider
                
            user = await self._get_cached_user(token, redis_client)

            if not user:
                user_data = None
                try:
                    cb_group: CircuitBreakerGroup = request.app.state.circuit_breaker_group
                    user_service_breaker = cb_group.get_breaker("user-service")
                    if user_service_breaker:
                        user_data = await user_service_breaker.call(self._validate_token, token)
                    else:
                        logger.warning("user-service circuit breaker not found. Calling service directly.")
                        user_data = await self._validate_token(token)
                except CircuitBreakerError as e:
                    logger.error(f"Circuit breaker open for user-service: {e}")
                    return Response('{"detail": "User service unavailable"}', status_code=503)
                except (AttributeError, KeyError):
                    logger.warning("Circuit breaker not in app state. Calling service directly.")
                    user_data = await self._validate_token(token)

                if user_data and isinstance(user_data, dict):
                    # Ensure required fields are present for UserContext
                    user_id = user_data.get("user_id")
                    if not user_id:
                        return Response('{"detail": "Invalid token: missing user_id"}', status_code=401)
                    
                    username = user_data.get("username", user_id) # Default username to user_id if missing
                    
                    user_context_data = {
                        "user_id": user_id,
                        "username": username,
                        "email": user_data.get("email"),
                        "roles": user_data.get("roles", []),
                        "permissions": user_data.get("permissions", []),
                        "metadata": user_data.get("metadata", {})
                    }
                    user = UserContext(**user_context_data)
                    await self._cache_user(token, user, redis_client)
                else:
                    return Response('{"detail": "Invalid token"}', status_code=401)
            
            request.state.user = user
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return Response('{"detail": "Internal server error"}', status_code=500)

        return await call_next(request)
    
    async def _get_cached_user(self, token: str, redis_client: redis.Redis) -> Optional[UserContext]:
        """Get user from Redis cache"""
        try:
            cached = await redis_client.get(f"auth_token:{token}")
            if cached:
                return UserContext.parse_raw(cached)
        except Exception as e:
            logger.error(f"Cache get failed: {e}")
        return None
    
    async def _cache_user(self, token: str, user: UserContext, redis_client: redis.Redis):
        """Cache user context in Redis"""
        try:
            await redis_client.setex(f"auth_token:{token}", self.cache_ttl, user.json())
        except Exception as e:
            logger.error(f"Cache set failed: {e}")

    async def _validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validates the JWT by calling the user-service."""
        headers = {"Authorization": f"Bearer {token}"}
        try:
            res = await self.client.get(f"{self.user_service_url}/auth/account/userinfo", headers=headers)
            res.raise_for_status()
            data = res.json()
            return {
                "user_id": data.get("id"),
                "username": data.get("username") or data.get("id"), # Fallback for username
                "email": data.get("email"),
                "roles": data.get("roles", []),
                "permissions": data.get("scopes", []),
                "metadata": {}
            }
        except httpx.RequestError as e:
            logger.error(f"Error calling user-service: {e}")
            return None
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None


def get_current_user(request: Request) -> UserContext:
    """
    현재 요청의 사용자 정보 반환
    FastAPI 의존성으로 사용
    """
    if not hasattr(request.state, 'user'):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return request.state.user