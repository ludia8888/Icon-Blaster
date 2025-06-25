#!/usr/bin/env python3
"""
Service-to-Service mTLS Client
서비스간 안전한 통신을 위한 mTLS 클라이언트
"""
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from prometheus_client import Counter, Histogram

from shared.security.mtls_config import create_mtls_client

# Metrics
SERVICE_REQUESTS_TOTAL = Counter(
    'oms_service_requests_total',
    'Total service-to-service requests',
    ['source_service', 'target_service', 'method', 'status']
)

SERVICE_REQUEST_DURATION = Histogram(
    'oms_service_request_duration_seconds',
    'Service-to-service request duration',
    ['source_service', 'target_service', 'method']
)

SERVICE_MTLS_ERRORS = Counter(
    'oms_service_mtls_errors_total',
    'mTLS connection errors between services',
    ['source_service', 'target_service', 'error_type']
)

logger = logging.getLogger(__name__)


class ServiceClient:
    """mTLS 기반 서비스 클라이언트"""

    SERVICE_URLS = {
        "schema-service": os.getenv("SCHEMA_SERVICE_URL", "https://schema-service:8443"),
        "branch-service": os.getenv("BRANCH_SERVICE_URL", "https://branch-service:8443"),
        "validation-service": os.getenv("VALIDATION_SERVICE_URL", "https://validation-service:8443"),
        "action-service": os.getenv("ACTION_SERVICE_URL", "https://action-service:8443"),
        "user-service": os.getenv("USER_SERVICE_URL", "https://user-service:8443"),
    }

    def __init__(self, source_service: str):
        self.source_service = source_service
        self.mtls_enabled = os.getenv("MTLS_ENABLED", "true").lower() == "true"
        self._clients: Dict[str, httpx.AsyncClient] = {}

    async def _get_client(self, target_service: str) -> httpx.AsyncClient:
        """서비스별 mTLS 클라이언트 가져오기"""
        if target_service not in self._clients:
            if self.mtls_enabled:
                try:
                    client = await create_mtls_client(self.source_service)
                    self._clients[target_service] = client
                    logger.info(f"mTLS client created: {self.source_service} -> {target_service}")
                except Exception as e:
                    logger.error(f"Failed to create mTLS client: {e}")
                    SERVICE_MTLS_ERRORS.labels(
                        source_service=self.source_service,
                        target_service=target_service,
                        error_type="client_creation_failed"
                    ).inc()
                    # Fallback to regular client
                    self._clients[target_service] = httpx.AsyncClient(timeout=30.0)
            else:
                # Regular HTTP client when mTLS is disabled
                base_url = self.SERVICE_URLS.get(target_service, f"http://{target_service}:8000")
                if self.mtls_enabled:
                    base_url = base_url.replace("https://", "http://").replace(":8443", ":8000")

                self._clients[target_service] = httpx.AsyncClient(
                    base_url=base_url,
                    timeout=30.0
                )

        return self._clients[target_service]

    async def request(
        self,
        method: str,
        target_service: str,
        endpoint: str,
        **kwargs
    ) -> httpx.Response:
        """서비스에 mTLS 요청 전송"""
        start_time = time.time()

        try:
            client = await self._get_client(target_service)
            base_url = self.SERVICE_URLS.get(target_service, f"https://{target_service}:8443")

            # Construct full URL
            if not endpoint.startswith('/'):
                endpoint = f'/{endpoint}'

            url = f"{base_url}{endpoint}"

            # Add service identification headers
            headers = kwargs.get('headers', {})
            headers.update({
                'X-Source-Service': self.source_service,
                'X-Request-ID': f"{self.source_service}-{int(time.time() * 1000)}",
                'User-Agent': f"OMS/{self.source_service}",
            })
            kwargs['headers'] = headers

            # Make request
            response = await client.request(method, url, **kwargs)

            # Record metrics
            SERVICE_REQUESTS_TOTAL.labels(
                source_service=self.source_service,
                target_service=target_service,
                method=method.upper(),
                status=str(response.status_code)
            ).inc()

            return response

        except Exception as e:
            logger.error(f"Service request failed: {self.source_service} -> {target_service} {method} {endpoint}: {e}")

            SERVICE_MTLS_ERRORS.labels(
                source_service=self.source_service,
                target_service=target_service,
                error_type=type(e).__name__
            ).inc()

            raise
        finally:
            duration = time.time() - start_time
            SERVICE_REQUEST_DURATION.labels(
                source_service=self.source_service,
                target_service=target_service,
                method=method.upper()
            ).observe(duration)

    async def get(self, target_service: str, endpoint: str, **kwargs) -> httpx.Response:
        """GET 요청"""
        return await self.request("GET", target_service, endpoint, **kwargs)

    async def post(self, target_service: str, endpoint: str, **kwargs) -> httpx.Response:
        """POST 요청"""
        return await self.request("POST", target_service, endpoint, **kwargs)

    async def put(self, target_service: str, endpoint: str, **kwargs) -> httpx.Response:
        """PUT 요청"""
        return await self.request("PUT", target_service, endpoint, **kwargs)

    async def delete(self, target_service: str, endpoint: str, **kwargs) -> httpx.Response:
        """DELETE 요청"""
        return await self.request("DELETE", target_service, endpoint, **kwargs)

    async def close(self):
        """모든 클라이언트 연결 종료"""
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()


class SchemaServiceClient:
    """Schema Service mTLS 클라이언트"""

    def __init__(self, source_service: str):
        self.client = ServiceClient(source_service)

    async def get_object_types(self, branch: str = "main") -> List[Dict[str, Any]]:
        """ObjectType 목록 조회"""
        response = await self.client.get(
            "schema-service",
            f"/api/v1/schemas/{branch}/object-types"
        )
        response.raise_for_status()
        return response.json()

    async def create_object_type(self, branch: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """ObjectType 생성"""
        response = await self.client.post(
            "schema-service",
            f"/api/v1/schemas/{branch}/object-types",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def get_object_type(self, branch: str, object_type_id: str) -> Optional[Dict[str, Any]]:
        """ObjectType 조회"""
        try:
            response = await self.client.get(
                "schema-service",
                f"/api/v1/schemas/{branch}/object-types/{object_type_id}"
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise


class BranchServiceClient:
    """Branch Service mTLS 클라이언트"""

    def __init__(self, source_service: str):
        self.client = ServiceClient(source_service)

    async def list_branches(self, include_system: bool = False) -> List[Dict[str, Any]]:
        """브랜치 목록 조회"""
        response = await self.client.get(
            "branch-service",
            "/api/v1/branches",
            params={"include_system": include_system}
        )
        response.raise_for_status()
        return response.json()

    async def create_branch(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """브랜치 생성"""
        response = await self.client.post(
            "branch-service",
            "/api/v1/branches",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def merge_branch(self, branch_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """브랜치 머지"""
        response = await self.client.post(
            "branch-service",
            f"/api/v1/branches/{branch_name}/merge",
            json=data
        )
        response.raise_for_status()
        return response.json()


class ValidationServiceClient:
    """Validation Service mTLS 클라이언트"""

    def __init__(self, source_service: str):
        self.client = ServiceClient(source_service)

    async def validate_breaking_changes(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Breaking changes 검증"""
        response = await self.client.post(
            "validation-service",
            "/api/v1/validation/breaking-changes",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def create_migration_plan(self, breaking_changes: List[Dict[str, Any]], target_branch: str = "main") -> Dict[str, Any]:
        """마이그레이션 계획 생성"""
        response = await self.client.post(
            "validation-service",
            "/api/v1/validation/migration-plan",
            json=breaking_changes,
            params={"target_branch": target_branch}
        )
        response.raise_for_status()
        return response.json()


class ActionServiceClient:
    """Action Service mTLS 클라이언트"""

    def __init__(self, source_service: str):
        self.client = ServiceClient(source_service)

    async def execute_action(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """액션 실행"""
        response = await self.client.post(
            "action-service",
            "/api/v1/actions/execute",
            json=data
        )
        response.raise_for_status()
        return response.json()

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """작업 상태 조회"""
        response = await self.client.get(
            "action-service",
            f"/api/v1/actions/jobs/{job_id}"
        )
        response.raise_for_status()
        return response.json()


class UserServiceClient:
    """User Service mTLS 클라이언트"""

    def __init__(self, source_service: str):
        self.client = ServiceClient(source_service)

    async def validate_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자 검증"""
        try:
            response = await self.client.get(
                "user-service",
                f"/api/v1/users/validate/{user_id}"
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    async def get_user_permissions(self, user_id: str) -> Dict[str, Any]:
        """사용자 권한 조회"""
        response = await self.client.get(
            "user-service",
            f"/api/v1/users/{user_id}/permissions"
        )
        response.raise_for_status()
        return response.json()


# Factory functions for easy client creation
def create_schema_client(source_service: str) -> SchemaServiceClient:
    """Schema Service 클라이언트 생성"""
    return SchemaServiceClient(source_service)

def create_branch_client(source_service: str) -> BranchServiceClient:
    """Branch Service 클라이언트 생성"""
    return BranchServiceClient(source_service)

def create_validation_client(source_service: str) -> ValidationServiceClient:
    """Validation Service 클라이언트 생성"""
    return ValidationServiceClient(source_service)

def create_action_client(source_service: str) -> ActionServiceClient:
    """Action Service 클라이언트 생성"""
    return ActionServiceClient(source_service)

def create_user_client(source_service: str) -> UserServiceClient:
    """User Service 클라이언트 생성"""
    return UserServiceClient(source_service)


@asynccontextmanager
async def get_service_client(source_service: str):
    """서비스 클라이언트 컨텍스트 매니저"""
    client = ServiceClient(source_service)
    try:
        yield client
    finally:
        await client.close()
