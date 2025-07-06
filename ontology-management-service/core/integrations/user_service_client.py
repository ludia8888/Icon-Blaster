"""
User Service Client
Handles JWT token validation and user information retrieval
"""
import os
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import HTTPException, status

from core.auth_utils import UserContext
from common_logging.setup import get_logger
from database.clients.unified_http_client import UnifiedHTTPClient, create_basic_client, HTTPClientConfig

logger = get_logger(__name__)


class UserServiceError(Exception):
    """User Service related errors"""
    pass


class UserServiceClient:
    """
    Client for interacting with User Service MSA
    Handles JWT validation and user context retrieval
    """
    
    def __init__(self):
        self.base_url = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
        self.timeout = 30.0
        
        # JWKS 지원 설정
        self.use_jwks = os.getenv("USE_JWKS", "false").lower() == "true"
        self.jwks_url = f"{self.base_url}/.well-known/jwks.json"
        self.jwks_cache = {}
        self.jwks_cache_ttl = 3600  # 1 hour
        self.jwks_last_update = 0
        
        # JWT secret for fallback (JWKS가 실패할 경우)
        self.jwt_secret = os.getenv("JWT_SECRET")
        if not self.jwt_secret and not self.use_jwks:
            raise ValueError(
                "JWT_SECRET environment variable is required when JWKS is disabled. "
                "Set it to a secure random value (e.g., openssl rand -base64 32)"
            )
        
        self.jwt_algorithm = "HS256"  # Fallback algorithm
        
        # JWT 검증 모드: local(로컬), remote(원격), jwks(JWKS)
        self.validation_mode = os.getenv("JWT_VALIDATION_MODE", "jwks" if self.use_jwks else "local")
        
        # Initialize HTTP client
        http_config = HTTPClientConfig(
            base_url=self.base_url,
            timeout=self.timeout,
            verify_ssl=False  # Maintaining original verify=False behavior
        )
        self._http_client = UnifiedHTTPClient(http_config)
    
    async def validate_jwt_token(self, token: str) -> UserContext:
        """
        Validate JWT token and return user context
        
        Args:
            token: JWT token string
            
        Returns:
            UserContext: Validated user information
            
        Raises:
            UserServiceError: If validation fails
        """
        # JWKS 우선 시도
        if self.validation_mode == "jwks" or self.use_jwks:
            try:
                return await self._validate_token_with_jwks(token)
            except Exception as e:
                logger.warning(f"JWKS validation failed: {e}, falling back to remote validation")
                return await self._validate_token_remote(token)
        elif self.validation_mode == "remote":
            return await self._validate_token_remote(token)
        else:
            return await self._validate_token_locally(token)
    
    async def _validate_token_locally(self, token: str) -> UserContext:
        """
        Validate JWT token locally (for development/testing)
        """
        try:
            # Decode JWT
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
                audience="oms"  # Accept tokens with 'oms' audience
            )
            
            # Check expiration
            exp = payload.get("exp")
            if exp and datetime.fromtimestamp(exp, tz=timezone.utc) < datetime.now(timezone.utc):
                raise UserServiceError("Token has expired")
            
            # Extract user information
            user_context = UserContext(
                user_id=payload.get("sub", payload.get("user_id")),
                username=payload.get("username", payload.get("preferred_username")),
                email=payload.get("email"),
                roles=payload.get("roles", []),
                tenant_id=payload.get("tenant_id"),
                metadata=payload.get("metadata", {})
            )
            
            # Validate required fields
            if not user_context.user_id or not user_context.username:
                raise UserServiceError("Invalid token: missing user_id or username")
            
            return user_context
            
        except jwt.ExpiredSignatureError:
            raise UserServiceError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise UserServiceError(f"Invalid token: {str(e)}")
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise UserServiceError(f"Token validation failed: {str(e)}")
    
    async def _validate_token_remote(self, token: str) -> UserContext:
        """
        Validate JWT token via User Service API
        """
        try:
            response = await self._http_client.post(
                "/api/v1/auth/validate",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                return UserContext(**data)
            elif response.status_code == 401:
                raise UserServiceError("Invalid or expired token")
            else:
                raise UserServiceError(
                    f"User service returned {response.status_code}: {response.text}"
                )
                
        except Exception as e:
            if "timeout" in str(e).lower():
                raise UserServiceError("User service timeout")
            else:
                logger.error(f"User service request error: {e}")
                raise UserServiceError(f"Failed to connect to user service: {str(e)}")
    
    async def get_user_by_id(self, user_id: str, auth_token: str) -> Dict[str, Any]:
        """
        Get detailed user information by ID
        """
        try:
            response = await self._http_client.get(
                f"/api/v1/users/{user_id}",
                headers={
                    "Authorization": f"Bearer {auth_token}"
                }
            )
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                raise UserServiceError(f"User {user_id} not found")
            else:
                raise UserServiceError(
                    f"Failed to get user: {response.status_code}"
                )
                
        except Exception as e:
            raise UserServiceError(f"Failed to get user: {str(e)}")
    
    async def get_user_roles(self, user_id: str, auth_token: str) -> List[str]:
        """
        Get user's roles from User Service
        """
        user_data = await self.get_user_by_id(user_id, auth_token)
        return user_data.get("roles", [])
    
    async def get_jwks(self) -> Optional[Dict[str, Any]]:
        """
        JWKS 키 조회 (캐싱 지원)
        """
        current_time = datetime.now(timezone.utc).timestamp()
        
        # 캐시 확인
        if (current_time - self.jwks_last_update) < self.jwks_cache_ttl and self.jwks_cache:
            return self.jwks_cache
        
        try:
            response = await self._http_client.get("/.well-known/jwks.json")
            
            if response.status_code == 200:
                jwks_data = response.json()
                self.jwks_cache = jwks_data
                self.jwks_last_update = current_time
                logger.info("JWKS keys updated successfully")
                return jwks_data
            else:
                logger.warning(f"JWKS request failed with status {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"JWKS request failed: {e}")
            return None
    
    async def _validate_token_with_jwks(self, token: str) -> UserContext:
        """
        JWKS를 사용한 JWT 토큰 검증
        """
        try:
            # JWKS 키 조회
            jwks_data = await self.get_jwks()
            if not jwks_data:
                raise UserServiceError("JWKS data not available")
            
            # 토큰 헤더에서 kid 추출
            header = jwt.get_unverified_header(token)
            kid = header.get('kid')
            
            if not kid:
                raise UserServiceError("Token has no kid in header")
            
            # 매칭되는 키 찾기
            matching_key = None
            for key in jwks_data.get('keys', []):
                if key.get('kid') == kid:
                    matching_key = key
                    break
            
            if not matching_key:
                raise UserServiceError(f"No matching key found for kid {kid}")
            
            # RSA 공개 키 구성
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.primitives import serialization
            import base64
            
            n = base64.urlsafe_b64decode(matching_key['n'] + '==')
            e = base64.urlsafe_b64decode(matching_key['e'] + '==')
            
            # 정수로 변환
            n_int = int.from_bytes(n, 'big')
            e_int = int.from_bytes(e, 'big')
            
            # RSA 공개 키 생성
            public_key = rsa.RSAPublicNumbers(e_int, n_int).public_key()
            
            # PEM 형식으로 직렬화
            pem_key = public_key.public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            )
            
            # 토큰 검증
            payload = jwt.decode(
                token,
                pem_key,
                algorithms=['RS256'],
                audience=os.getenv('JWT_AUDIENCE', 'oms'),
                issuer=os.getenv('JWT_ISSUER', 'user-service')
            )
            
            # UserContext 생성
            user_context = UserContext(
                user_id=payload.get("sub", payload.get("user_id")),
                username=payload.get("username", payload.get("preferred_username")),
                email=payload.get("email"),
                roles=payload.get("roles", []),
                permissions=payload.get("permissions", []),
                tenant_id=payload.get("tenant_id"),
                metadata=payload
            )
            
            # 필수 필드 검증
            if not user_context.user_id or not user_context.username:
                raise UserServiceError("Invalid token: missing user_id or username")
            
            return user_context
            
        except jwt.ExpiredSignatureError:
            raise UserServiceError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise UserServiceError(f"Invalid token: {str(e)}")
        except Exception as e:
            logger.error(f"JWKS token validation error: {e}")
            raise UserServiceError(f"JWKS token validation failed: {str(e)}")


# Global client instance (lazy-initialized)
_user_service_client = None


def _get_user_service_client() -> UserServiceClient:
    """Get or create the global user service client"""
    global _user_service_client
    if _user_service_client is None:
        _user_service_client = UserServiceClient()
    return _user_service_client


async def validate_jwt_token(token: str) -> UserContext:
    """
    Global function to validate JWT token
    Used by AuthMiddleware
    """
    client = _get_user_service_client()
    return await client.validate_jwt_token(token)


def create_mock_jwt(
    user_id: str = "test-user",
    username: str = "testuser",
    roles: List[str] = None,
    expires_in: int = 3600
) -> str:
    """
    Create a mock JWT token for testing
    """
    if roles is None:
        roles = ["developer"]
    
    payload = {
        "sub": user_id,
        "username": username,
        "email": f"{username}@example.com",
        "roles": roles,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "iat": datetime.now(timezone.utc),
        "tenant_id": "default"
    }
    
    client = _get_user_service_client()
    return jwt.encode(
        payload,
        client.jwt_secret,
        algorithm=client.jwt_algorithm
    )