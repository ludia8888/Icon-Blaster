"""
Base Resolver - 모든 리졸버의 기본 클래스 및 공통 기능
"""
import os
import logging
from typing import Optional, Dict, Any
import httpx
from core.auth import UserContext as User

logger = logging.getLogger(__name__)


class ServiceClient:
    """마이크로서비스 통신을 위한 클라이언트"""
    
    def __init__(self):
        self.schema_service_url = os.getenv("SCHEMA_SERVICE_URL", "http://schema-service:8000")
        self.branch_service_url = os.getenv("BRANCH_SERVICE_URL", "http://branch-service:8000")
        self.validation_service_url = os.getenv("VALIDATION_SERVICE_URL", "http://validation-service:8000")
        self.action_service_url = os.getenv("ACTION_SERVICE_URL", "http://action-service:8000")
        self.function_service_url = os.getenv("FUNCTION_SERVICE_URL", "http://function-service:8000")
        self.data_service_url = os.getenv("DATA_SERVICE_URL", "http://data-service:8000")

    async def get_auth_headers(self, user: Optional[User]) -> dict:
        """인증 헤더 생성"""
        if user and hasattr(user, 'access_token'):
            return {"Authorization": f"Bearer {user.access_token}"}
        elif user:
            return {"Authorization": f"Bearer {user.user_id}"}
        return {}

    async def call_service(
        self, 
        url: str, 
        method: str = "GET", 
        json_data: dict = None, 
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """서비스 호출"""
        headers = await self.get_auth_headers(user)
        headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient() as client:
            response = await client.request(
                method, 
                url, 
                json=json_data, 
                headers=headers,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()


class BaseResolver:
    """모든 리졸버의 기본 클래스"""
    
    def __init__(self):
        self.service_client = ServiceClient()
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def get_current_user(self, info) -> Optional[User]:
        """현재 사용자 정보 조회"""
        return info.context.get("user")
    
    def log_operation(self, operation: str, **kwargs):
        """작업 로깅"""
        self.logger.info(f"{operation} - {kwargs}")
    
    async def handle_service_error(self, error: Exception, operation: str):
        """서비스 에러 처리"""
        self.logger.error(f"Service error in {operation}: {str(error)}")
        if isinstance(error, httpx.HTTPStatusError):
            if error.response.status_code == 404:
                return None
            elif error.response.status_code == 403:
                raise PermissionError(f"Access denied for {operation}")
        raise error