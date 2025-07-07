"""
Action Metadata Service
OMS 내부 ActionType 메타데이터 관리만 담당
실제 실행은 Actions Service MSA에서 처리
"""
import logging
import httpx
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import asyncio

from database.clients.unified_http_client import UnifiedHTTPClient, create_basic_client, HTTPClientConfig
from shared.cache.smart_cache import SmartCacheManager
from database.clients.terminus_db import TerminusDBClient
from core.action.metadata_service import ActionMetadataService

logger = logging.getLogger(__name__)


class ActionService:
    """
    OMS Action Service - 메타데이터 관리만 담당
    실제 실행은 Actions Service MSA로 위임
    """

    def __init__(
        self,
        tdb_client: TerminusDBClient,
        redis_client,
        event_publisher: Optional[Any] = None,
        actions_service_url: str = None
    ):
        self.tdb = tdb_client
        self.cache = SmartCacheManager(tdb_client)
        self.redis = redis_client
        self.event_publisher = event_publisher
        self.actions_service_url = actions_service_url or os.getenv("ACTIONS_SERVICE_URL", "http://actions-service:8009")
        
        # 메타데이터 서비스 초기화 (기존 방식 유지)
        self.metadata_service = ActionMetadataService(tdb_client, redis_client)
        
        # Initialize HTTP client for Actions Service MSA communication
        http_config = HTTPClientConfig(
            base_url=self.actions_service_url,
            timeout=30.0
        )
        self._http_client = UnifiedHTTPClient(http_config)

    # ActionType 메타데이터 관리 (CRUD)
    async def create_action_type(self, action_definition: Dict[str, Any]) -> str:
        """ActionType 메타데이터 생성"""
        action_type = await self.metadata_service.create_action_type(action_definition)
        return action_type.id

    async def get_action_type(self, action_type_id: str) -> Optional[Dict[str, Any]]:
        """ActionType 메타데이터 조회"""
        action_type = await self.metadata_service.get_action_type(action_type_id)
        return action_type.model_dump(mode="json") if action_type else None

    async def update_action_type(self, action_type_id: str, updates: Dict[str, Any]) -> bool:
        """ActionType 메타데이터 업데이트"""
        updated = await self.metadata_service.update_action_type(action_type_id, updates)
        return updated is not None

    async def delete_action_type(self, action_type_id: str) -> bool:
        """ActionType 메타데이터 삭제"""
        return await self.metadata_service.delete_action_type(action_type_id)

    async def list_action_types(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """ActionType 목록 조회"""
        kwargs = filters if filters else {}
        action_types = await self.metadata_service.list_action_types(**kwargs)
        return [action.model_dump(mode="json") for action in action_types]

    async def validate_action_schema(self, action_definition: Dict[str, Any]) -> Dict[str, Any]:
        """ActionType 스키마 검증"""
        action_type_id = action_definition.get("id")
        parameters = action_definition.get("parameters", {})
        
        if not action_type_id:
            return {"valid": False, "errors": ["ActionType ID is missing in definition"]}
        
        return await self.metadata_service.validate_action_input(
            action_type_id=action_type_id,
            parameters=parameters
        )

    # 실행 관련 메서드들 - Actions Service MSA로 위임
    async def execute_action(
        self,
        action_type_id: str,
        object_ids: List[str],
        parameters: Dict[str, Any],
        user: Dict[str, Any],
        execution_options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        액션 실행 - Actions Service MSA로 위임
        """
        response = await self._http_client.post(
            "/actions/apply",
            json={
                "action_type_id": action_type_id,
                "object_ids": object_ids,
                "parameters": parameters,
                "user": user,
                "execution_options": execution_options or {}
            }
        )
        if response.status_code >= 400:
            raise Exception(f"Action execution failed: {response.status_code}")
        return response.json()

    async def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """
        실행 상태 조회 - Actions Service MSA로 위임
        """
        response = await self._http_client.get(
            f"/actions/execution/{execution_id}/status"
        )
        if response.status_code >= 400:
            raise Exception(f"Execution status query failed: {response.status_code}")
        return response.json()

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Job 상태 조회 - Actions Service MSA로 위임
        """
        response = await self._http_client.get(
            f"/actions/job/{job_id}/status"
        )
        if response.status_code >= 400:
            raise Exception(f"Job status query failed: {response.status_code}")
        return response.json()

    # 테스트 호환성 메서드들
    async def start_workers(self, num_workers: int = 3):
        """테스트 호환성: 실제 워커는 Actions Service에서 관리"""
        logger.info(f"Worker management delegated to Actions Service MSA at {self.actions_service_url}")
        return True

    async def stop_workers(self):
        """테스트 호환성: 실제 워커는 Actions Service에서 관리"""
        logger.info("Worker shutdown delegated to Actions Service MSA")
        return True

    async def get_worker_status(self) -> Dict[str, Any]:
        """워커 상태 조회 - Actions Service MSA로 위임"""
        try:
            response = await self._http_client.get(
                "/actions/workers/status"
            )
            if response.status_code >= 400:
                raise Exception(f"Worker status query failed: {response.status_code}")
            return response.json()
        except Exception as e:
            logger.warning(f"Failed to get worker status from Actions Service: {e}")
            return {"status": "unknown", "workers": 0}

    # Legacy 호환성 메서드들
    def register_action_type(self, action_type: Any) -> str:
        """Legacy 호환성: create_action_type 사용 권장"""
        if hasattr(action_type, 'dict'):
            return asyncio.run(self.create_action_type(action_type.model_dump()))
        return asyncio.run(self.create_action_type(action_type))

    def execute_sync(self, *args, **kwargs) -> Any:
        """Legacy 호환성: execute_action 사용 권장"""
        return asyncio.run(self.execute_action(*args, **kwargs))