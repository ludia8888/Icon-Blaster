"""
User Service Client for OMS
OMS가 User Service와 통신하기 위한 클라이언트
"""
import asyncio
import httpx
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel
from models import UserContext

class UserInfo(BaseModel):
    """사용자 정보 모델"""
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    roles: List[str] = []
    permissions: List[str] = []
    status: str = "active"
    last_login: Optional[datetime] = None

class Permission(BaseModel):
    """권한 모델"""
    resource_type: str
    resource_id: str
    action: str

class TokenValidationResponse(BaseModel):
    """토큰 검증 응답 모델"""
    valid: bool
    user_id: Optional[str] = None
    username: Optional[str] = None
    roles: List[str] = []
    permissions: List[str] = []
    expires_at: Optional[datetime] = None

class UserServiceError(Exception):
    """User Service 통신 오류"""
    pass

class UserServiceClient:
    """
    User Service와 통신하는 클라이언트
    JWT 토큰 검증, 사용자 정보 조회, 권한 확인 등을 담당
    """
    
    def __init__(self, base_url: str = "http://localhost:8000", timeout: int = 10):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("UserServiceClient must be used as async context manager")
        return self._client
    
    async def validate_token(self, token: str) -> UserContext:
        """
        JWT 토큰 검증 및 사용자 컨텍스트 반환
        
        Args:
            token: JWT 토큰
            
        Returns:
            UserContext: 검증된 사용자 컨텍스트
            
        Raises:
            UserServiceError: 토큰 검증 실패 시
        """
        try:
            response = await self.client.get(
                "/auth/validate",
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if response.status_code == 200:
                data = response.json()
                validation_result = TokenValidationResponse(**data)
                
                if validation_result.valid and validation_result.user_id:
                    return UserContext(
                        id=int(validation_result.user_id),
                        username=validation_result.username or "",
                        email="",  # 별도 조회 필요시 get_user_info 사용
                        roles=validation_result.roles
                    )
            
            raise UserServiceError(f"Token validation failed: {response.status_code}")
            
        except httpx.RequestError as e:
            raise UserServiceError(f"Failed to communicate with User Service: {e}")
    
    async def get_user_info(self, user_id: str) -> UserInfo:
        """
        사용자 정보 조회
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            UserInfo: 사용자 정보
            
        Raises:
            UserServiceError: 사용자 조회 실패 시
        """
        try:
            response = await self.client.get(f"/users/{user_id}")
            
            if response.status_code == 200:
                data = response.json()
                return UserInfo(**data)
            elif response.status_code == 404:
                raise UserServiceError(f"User not found: {user_id}")
            else:
                raise UserServiceError(f"Failed to get user info: {response.status_code}")
                
        except httpx.RequestError as e:
            raise UserServiceError(f"Failed to communicate with User Service: {e}")
    
    async def get_user_permissions(self, user_id: str) -> List[Permission]:
        """
        사용자 권한 목록 조회
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            List[Permission]: 권한 목록
            
        Raises:
            UserServiceError: 권한 조회 실패 시
        """
        try:
            response = await self.client.get(f"/users/{user_id}/permissions")
            
            if response.status_code == 200:
                data = response.json()
                return [Permission(**perm) for perm in data.get("permissions", [])]
            else:
                raise UserServiceError(f"Failed to get user permissions: {response.status_code}")
                
        except httpx.RequestError as e:
            raise UserServiceError(f"Failed to communicate with User Service: {e}")
    
    async def check_permission(self, user_id: str, resource_type: str, resource_id: str, action: str) -> bool:
        """
        사용자 권한 확인
        
        Args:
            user_id: 사용자 ID
            resource_type: 리소스 타입 (schema, branch, validation 등)
            resource_id: 리소스 ID (* for all)
            action: 액션 (read, create, update, delete 등)
            
        Returns:
            bool: 권한 있음 여부
        """
        try:
            permissions = await self.get_user_permissions(user_id)
            
            # 관리자 권한 확인
            admin_perms = [p for p in permissions if p.resource_type == "*" and p.action == "*"]
            if admin_perms:
                return True
            
            # 구체적 권한 확인
            for perm in permissions:
                if (perm.resource_type == resource_type or perm.resource_type == "*") and \
                   (perm.resource_id == resource_id or perm.resource_id == "*") and \
                   (perm.action == action or perm.action == "*"):
                    return True
            
            return False
            
        except UserServiceError:
            # 권한 조회 실패시 안전하게 False 반환
            return False
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, str]:
        """
        리프레시 토큰으로 새 토큰 발급
        
        Args:
            refresh_token: 리프레시 토큰
            
        Returns:
            Dict[str, str]: 새로운 토큰 쌍 {"access_token": "...", "refresh_token": "..."}
            
        Raises:
            UserServiceError: 토큰 갱신 실패 시
        """
        try:
            response = await self.client.post(
                "/auth/refresh",
                json={"refresh_token": refresh_token}
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise UserServiceError(f"Token refresh failed: {response.status_code}")
                
        except httpx.RequestError as e:
            raise UserServiceError(f"Failed to communicate with User Service: {e}")
    
    async def health_check(self) -> bool:
        """
        User Service 헬스체크
        
        Returns:
            bool: 서비스 정상 여부
        """
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except:
            return False

# 싱글톤 클라이언트 인스턴스
_user_service_client: Optional[UserServiceClient] = None

def get_user_service_client() -> UserServiceClient:
    """User Service 클라이언트 인스턴스 반환"""
    global _user_service_client
    if _user_service_client is None:
        _user_service_client = UserServiceClient()
    return _user_service_client

# 편의 함수들
async def validate_jwt_token(token: str) -> UserContext:
    """JWT 토큰 검증 편의 함수"""
    async with get_user_service_client() as client:
        return await client.validate_token(token)

async def check_user_permission(user_id: str, resource_type: str, resource_id: str, action: str) -> bool:
    """사용자 권한 확인 편의 함수"""
    async with get_user_service_client() as client:
        return await client.check_permission(user_id, resource_type, resource_id, action)