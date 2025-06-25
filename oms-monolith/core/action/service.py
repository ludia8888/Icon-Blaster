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

# Lightweight imports - OMS should be self-contained
try:
    # Try importing from shared if available
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../shared'))
    from shared.cache.smart_cache import SmartCacheManager
    from database.clients.terminus_db import TerminusDBClient
except ImportError:
    # Fallback to stub implementations for OMS self-containment
    class SmartCacheManager:
        def __init__(self, *args, **kwargs):
            pass
    
    class TerminusDBClient:
        def __init__(self, *args, **kwargs):
            pass
from .metadata_service import ActionMetadataService

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
        
        # 메타데이터 서비스만 초기화
        self.metadata_service = ActionMetadataService(tdb_client, redis_client)

    # ActionType 메타데이터 관리 (CRUD)
    async def create_action_type(self, action_definition: Dict[str, Any]) -> str:
        """ActionType 메타데이터 생성"""
        action_type = await self.metadata_service.create_action_type(action_definition)
        return action_type.id  # ActionType ID 반환

    async def get_action_type(self, action_type_id: str) -> Optional[Dict[str, Any]]:
        """ActionType 메타데이터 조회"""
        return await self.metadata_service.get_action_type(action_type_id)

    async def update_action_type(self, action_type_id: str, updates: Dict[str, Any]) -> bool:
        """ActionType 메타데이터 업데이트"""
        return await self.metadata_service.update_action_type(action_type_id, updates)

    async def delete_action_type(self, action_type_id: str) -> bool:
        """ActionType 메타데이터 삭제"""
        return await self.metadata_service.delete_action_type(action_type_id)

    async def list_action_types(self, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """ActionType 목록 조회"""
        return await self.metadata_service.list_action_types(filters)

    async def validate_action_schema(self, action_definition: Dict[str, Any]) -> Dict[str, Any]:
        """ActionType 스키마 검증"""
        return await self.metadata_service.validate_action_schema(action_definition)

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
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.actions_service_url}/actions/apply",
                json={
                    "action_type_id": action_type_id,
                    "object_ids": object_ids,
                    "parameters": parameters,
                    "user": user,
                    "execution_options": execution_options or {}
                },
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()

    async def get_execution_status(self, execution_id: str) -> Dict[str, Any]:
        """
        실행 상태 조회 - Actions Service MSA로 위임
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.actions_service_url}/actions/execution/{execution_id}/status",
                timeout=10.0
            )
            response.raise_for_status()
            return response.json()

    async def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Job 상태 조회 - Actions Service MSA로 위임
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.actions_service_url}/actions/job/{job_id}/status",
                timeout=10.0
            )
            response.raise_for_status()
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
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.actions_service_url}/actions/workers/status",
                    timeout=5.0
                )
                response.raise_for_status()
                return response.json()
            except Exception as e:
                logger.warning(f"Failed to get worker status from Actions Service: {e}")
                return {"status": "unknown", "workers": 0}

    # Legacy 호환성 메서드들
    def register_action_type(self, action_type: Any) -> str:
        """Legacy 호환성: create_action_type 사용 권장"""
        if hasattr(action_type, 'dict'):
            return asyncio.run(self.create_action_type(action_type.dict()))
        return asyncio.run(self.create_action_type(action_type))

    def execute_sync(self, *args, **kwargs) -> Any:
        """Legacy 호환성: execute_action 사용 권장"""
        return asyncio.run(self.execute_action(*args, **kwargs))