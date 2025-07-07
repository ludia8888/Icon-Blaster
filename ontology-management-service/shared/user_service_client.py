"""
User Service Client for Auth Integration
완전한 user-service 통합을 위한 HTTP 클라이언트
"""
import os
import httpx
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import asyncio
from urllib.parse import urljoin

from core.auth_utils import UserContext
from common_logging.setup import get_logger

logger = get_logger(__name__)


class UserServiceClient:
    """User Service HTTP 클라이언트"""
    
    def __init__(self):
        self.base_url = os.getenv('USER_SERVICE_URL', 'http://user-service:8000')
        self.timeout = 30.0
        self.max_retries = 3
        self.session = None
        
    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        self.session = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        if self.session:
            await self.session.aclose()
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """HTTP 요청 실행"""
        url = urljoin(self.base_url, endpoint)
        
        for attempt in range(self.max_retries):
            try:
                if not self.session:
                    self.session = httpx.AsyncClient(
                        base_url=self.base_url,
                        timeout=self.timeout
                    )
                
                response = await self.session.request(method, endpoint, **kwargs)
                response.raise_for_status()
                
                return response.json()
                
            except httpx.TimeoutException:
                logger.warning(f"User service timeout on attempt {attempt + 1}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(1)
                
            except httpx.HTTPStatusError as e:
                logger.error(f"User service HTTP error: {e.response.status_code} - {e.response.text}")
                raise
                
            except Exception as e:
                logger.error(f"User service request failed: {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(1)
    
    async def login(self, username: str, password: str, mfa_code: Optional[str] = None) -> Dict[str, Any]:
        """사용자 로그인 - 2단계 인증 처리"""
        # Step 1: Username/password authentication
        step1_data = {
            "username": username,
            "password": password
        }
        
        try:
            step1_response = await self._request("POST", "/auth/login", json=step1_data)
            
            # Check if this is a challenge response
            if step1_response.get("step") == "mfa_required" or step1_response.get("challenge_token"):
                challenge_token = step1_response.get("challenge_token")
                
                # Step 2: Complete authentication with challenge token
                step2_data = {
                    "challenge_token": challenge_token,
                    "mfa_code": mfa_code  # Can be None for non-MFA users
                }
                
                step2_response = await self._request("POST", "/auth/login/complete", json=step2_data)
                return step2_response
            
            # If no challenge required, return the response (legacy flow)
            return step1_response
            
        except httpx.HTTPStatusError as e:
            # If step 1 fails, it might be using legacy endpoint
            if e.response.status_code == 404:
                # Try legacy endpoint
                legacy_data = {
                    "username": username,
                    "password": password
                }
                if mfa_code:
                    legacy_data["mfa_code"] = mfa_code
                    
                return await self._request("POST", "/auth/login/legacy", json=legacy_data)
            raise
    
    async def register(self, username: str, email: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
        """사용자 회원가입"""
        data = {
            "username": username,
            "email": email,
            "password": password,
            "full_name": full_name
        }
        
        return await self._request("POST", "/auth/register", json=data)
    
    async def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """JWT 토큰 검증"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = await self._request("GET", "/auth/userinfo", headers=headers)
            return response
        except Exception as e:
            logger.debug(f"Token validation failed: {e}")
            return None
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """토큰 갱신"""
        data = {"refresh_token": refresh_token}
        return await self._request("POST", "/auth/refresh", json=data)
    
    async def change_password(self, token: str, old_password: str, new_password: str) -> Dict[str, Any]:
        """비밀번호 변경"""
        headers = {"Authorization": f"Bearer {token}"}
        data = {
            "old_password": old_password,
            "new_password": new_password
        }
        return await self._request("POST", "/auth/change-password", json=data, headers=headers)
    
    async def logout(self, token: str) -> Dict[str, Any]:
        """로그아웃"""
        headers = {"Authorization": f"Bearer {token}"}
        return await self._request("POST", "/auth/logout", headers=headers)
    
    async def get_user_info(self, token: str) -> Optional[Dict[str, Any]]:
        """사용자 정보 조회"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            return await self._request("GET", "/auth/userinfo", headers=headers)
        except Exception as e:
            logger.debug(f"Failed to get user info: {e}")
            return None
    
    async def setup_mfa(self, token: str) -> Dict[str, Any]:
        """MFA 설정"""
        headers = {"Authorization": f"Bearer {token}"}
        return await self._request("POST", "/auth/mfa/setup", headers=headers)
    
    async def enable_mfa(self, token: str, code: str) -> Dict[str, Any]:
        """MFA 활성화"""
        headers = {"Authorization": f"Bearer {token}"}
        data = {"code": code}
        return await self._request("POST", "/auth/mfa/enable", json=data, headers=headers)
    
    async def disable_mfa(self, token: str, password: str, code: str) -> Dict[str, Any]:
        """MFA 비활성화"""
        headers = {"Authorization": f"Bearer {token}"}
        data = {"password": password, "code": code}
        return await self._request("POST", "/auth/mfa/disable", json=data, headers=headers)
    
    async def check_permission(self, token: str, user_id: str, resource_type: str, resource_id: str, action: str) -> bool:
        """권한 확인"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            params = {
                "user_id": user_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action
            }
            response = await self._request("POST", "/auth/check-permission", params=params, headers=headers)
            return response.get("allowed", False)
        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            return False
    
    async def get_jwks(self) -> Dict[str, Any]:
        """JWKS 키 조회"""
        return await self._request("GET", "/.well-known/jwks.json")
    
    async def health_check(self) -> bool:
        """Health Check"""
        try:
            await self._request("GET", "/health")
            return True
        except Exception:
            return False


# 전역 클라이언트 인스턴스
_user_service_client: Optional[UserServiceClient] = None


def get_user_service_client() -> UserServiceClient:
    """User Service 클라이언트 인스턴스 가져오기"""
    global _user_service_client
    if _user_service_client is None:
        _user_service_client = UserServiceClient()
    return _user_service_client


async def validate_jwt_token_via_user_service(token: str) -> Optional[UserContext]:
    """User Service를 통한 JWT 토큰 검증"""
    client = get_user_service_client()
    
    try:
        async with client:
            user_data = await client.validate_token(token)
            
            if user_data:
                return UserContext(
                    user_id=user_data.get("user_id"),
                    username=user_data.get("username"),
                    email=user_data.get("email"),
                    roles=user_data.get("roles", []),
                    permissions=user_data.get("permissions", []),
                    is_authenticated=True,
                    tenant_id=user_data.get("tenant_id"),
                    metadata=user_data
                )
    except Exception as e:
        logger.warning(f"User service token validation failed: {e}")
        
    return None


async def login_via_user_service(username: str, password: str, mfa_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """User Service를 통한 로그인"""
    client = get_user_service_client()
    
    try:
        async with client:
            return await client.login(username, password, mfa_code)
    except Exception as e:
        logger.error(f"User service login failed: {e}")
        return None


async def register_via_user_service(username: str, email: str, password: str, full_name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """User Service를 통한 회원가입"""
    client = get_user_service_client()
    
    try:
        async with client:
            return await client.register(username, email, password, full_name)
    except Exception as e:
        logger.error(f"User service registration failed: {e}")
        return None


# 백워드 호환성을 위한 기존 함수들
async def validate_jwt_token(token: str) -> Optional[UserContext]:
    """JWT 토큰 검증 (User Service 우선)"""
    return await validate_jwt_token_via_user_service(token)


async def get_user_by_token(token: str) -> Optional[UserContext]:
    """토큰으로 사용자 정보 조회"""
    return await validate_jwt_token_via_user_service(token)