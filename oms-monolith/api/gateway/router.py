"""
요청 라우팅
서비스로 요청 전달
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import httpx

from api.gateway.models import RequestContext, ServiceRoute
from database.clients.unified_http_client import UnifiedHTTPClient, create_basic_client, HTTPClientConfig

logger = logging.getLogger(__name__)


class ServiceUnavailableError(Exception):
    """서비스 사용 불가 오류"""
    pass


class RequestRouter:
    """요청 라우터"""

    def __init__(self, routes: List[ServiceRoute], circuit_breaker=None):
        self.routes = routes
        self.circuit_breaker = circuit_breaker
        self.route_map = self._build_route_map()
        self.http_client = create_basic_client(timeout=30.0)

    def _build_route_map(self) -> Dict[str, ServiceRoute]:
        """라우트 맵 구성"""
        route_map = {}
        for route in self.routes:
            route_map[route.path_pattern] = route
        return route_map

    async def route_request(
        self,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        context: RequestContext
    ) -> Tuple[int, Dict[str, str], bytes]:
        """요청 라우팅"""

        # 매칭되는 라우트 찾기
        route = self._find_matching_route(method, path)
        if not route:
            return 404, {}, b'{"error": "Route not found"}'

        # 서비스 URL 구성
        service_url = self._build_service_url(route, path)

        # 헤더 준비
        forward_headers = self._prepare_headers(headers, context)

        # Circuit breaker 확인
        if self.circuit_breaker and route.circuit_breaker_enabled:
            if not await self.circuit_breaker.is_closed(route.service_name):
                raise ServiceUnavailableError(f"Service {route.service_name} is unavailable")

        # 요청 전달
        try:
            response = await self._forward_request(
                method=method,
                url=service_url,
                headers=forward_headers,
                body=body,
                timeout=route.timeout,
                retry_count=route.retry_count,
                service_name=route.service_name
            )

            # Circuit breaker 성공 기록
            if self.circuit_breaker and route.circuit_breaker_enabled:
                await self.circuit_breaker.record_success(route.service_name)

            return response

        except Exception:
            # Circuit breaker 실패 기록
            if self.circuit_breaker and route.circuit_breaker_enabled:
                await self.circuit_breaker.record_failure(route.service_name)
            raise

    def _find_matching_route(self, method: str, path: str) -> Optional[ServiceRoute]:
        """매칭되는 라우트 찾기"""

        for pattern, route in self.route_map.items():
            if self._match_pattern(pattern, path) and method in route.methods:
                return route
        return None

    def _match_pattern(self, pattern: str, path: str) -> bool:
        """경로 패턴 매칭"""

        # 간단한 패턴 매칭 (실제로는 더 복잡한 로직 필요)
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            return path.startswith(prefix)
        else:
            return path == pattern or path.startswith(pattern + "/")

    def _build_service_url(self, route: ServiceRoute, path: str) -> str:
        """서비스 URL 구성"""

        # 특별한 경우 처리: /object-types/{id} -> /api/v1/schemas/main/object-types/{id}
        if path.startswith("/object-types/") and route.service_name == "schema-service":
            object_id = path[len("/object-types/"):]
            service_path = f"/api/v1/schemas/main/object-types/{object_id}"
        # 특별한 경우 처리: /validation/breaking-changes -> /api/v1/validation/breaking-changes
        elif path == "/validation/breaking-changes" and route.service_name == "validation-service":
            service_path = "/api/v1/validation/breaking-changes"
        # Prefix 제거 처리
        elif route.strip_prefix and path.startswith(route.path_pattern.rstrip("/*")):
            service_path = path[len(route.path_pattern.rstrip("/*")):]
            if not service_path.startswith("/"):
                service_path = "/" + service_path
        else:
            service_path = path

        return urljoin(route.service_url, service_path)

    def _prepare_headers(self, headers: Dict[str, str], context: RequestContext) -> Dict[str, str]:
        """전달할 헤더 준비"""

        # 기본 헤더 복사
        forward_headers = dict(headers)

        # Gateway 관련 헤더 제거
        for header in ["host", "content-length", "connection"]:
            forward_headers.pop(header, None)

        # 컨텍스트 헤더 추가
        forward_headers.update({
            "X-Request-ID": context.request_id,
            "X-Forwarded-For": context.client_ip,
            "X-Gateway-Time": datetime.utcnow().isoformat()
        })

        if context.user_id:
            forward_headers["X-User-ID"] = context.user_id
            forward_headers["X-User-Roles"] = ",".join(context.user_roles)

        return forward_headers

    async def _forward_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        timeout: int,
        retry_count: int,
        service_name: str
    ) -> Tuple[int, Dict[str, str], bytes]:
        """요청 전달 with retry"""

        last_error = None

        for attempt in range(retry_count):
            try:
                response = await self.http_client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    content=body,
                    timeout=timeout
                )

                # 응답 헤더 정리
                response_headers = dict(response.headers)
                response_headers.pop("content-encoding", None)  # Gateway에서 처리
                response_headers.pop("transfer-encoding", None)

                return response.status_code, response_headers, response.content

            except httpx.TimeoutException as e:
                last_error = e
                logger.warning(f"Timeout calling {service_name} (attempt {attempt + 1}/{retry_count})")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

            except httpx.HTTPError as e:
                last_error = e
                logger.error(f"HTTP error calling {service_name}: {e}")
                if attempt < retry_count - 1:
                    await asyncio.sleep(2 ** attempt)

            except Exception as e:
                last_error = e
                logger.error(f"Unexpected error calling {service_name}: {e}")
                break

        # 모든 재시도 실패
        if isinstance(last_error, httpx.TimeoutException):
            return 504, {}, b'{"error": "Gateway timeout"}'
        else:
            return 502, {}, f'{{"error": "Bad gateway: {str(last_error)}"}}'.encode()

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self.http_client.aclose()


class LoadBalancer:
    """로드 밸런서"""

    def __init__(self, strategy: str = "round_robin"):
        self.strategy = strategy
        self.current_index = {}
        self.health_status = {}

    def get_next_instance(self, service_name: str, instances: List[str]) -> Optional[str]:
        """다음 인스턴스 선택"""

        # 건강한 인스턴스만 필터링
        healthy_instances = [
            inst for inst in instances
            if self.health_status.get(f"{service_name}:{inst}", True)
        ]

        if not healthy_instances:
            return None

        if self.strategy == "round_robin":
            # Round-robin 선택
            if service_name not in self.current_index:
                self.current_index[service_name] = 0

            index = self.current_index[service_name] % len(healthy_instances)
            self.current_index[service_name] = (index + 1) % len(healthy_instances)

            return healthy_instances[index]

        elif self.strategy == "random":
            # 랜덤 선택
            import random
            return random.choice(healthy_instances)

        else:
            # 기본: 첫 번째 인스턴스
            return healthy_instances[0]

    def mark_unhealthy(self, service_name: str, instance: str):
        """인스턴스를 비정상으로 표시"""
        key = f"{service_name}:{instance}"
        self.health_status[key] = False
        logger.warning(f"Marked {key} as unhealthy")

    def mark_healthy(self, service_name: str, instance: str):
        """인스턴스를 정상으로 표시"""
        key = f"{service_name}:{instance}"
        self.health_status[key] = True
        logger.info(f"Marked {key} as healthy")
