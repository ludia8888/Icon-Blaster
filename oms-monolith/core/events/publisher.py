"""
Event Publisher for OMS
OMS에서 발생하는 이벤트를 Audit Service로 발행
"""
import asyncio
import json
import httpx
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from uuid import uuid4
from dataclasses import dataclass, asdict
from enum import Enum

class EventType(str, Enum):
    """OMS 이벤트 타입"""
    # 스키마 관련
    SCHEMA_CREATED = "oms.schema.created"
    SCHEMA_UPDATED = "oms.schema.updated"
    SCHEMA_DELETED = "oms.schema.deleted"
    SCHEMA_VALIDATED = "oms.schema.validated"
    
    # 브랜치 관련
    BRANCH_CREATED = "oms.branch.created"
    BRANCH_MERGED = "oms.branch.merged"
    BRANCH_DELETED = "oms.branch.deleted"
    
    # 검증 관련
    VALIDATION_PASSED = "oms.validation.passed"
    VALIDATION_FAILED = "oms.validation.failed"
    VALIDATION_RULE_CREATED = "oms.validation.rule.created"
    
    # 액션 관련
    ACTION_EXECUTED = "oms.action.executed"
    ACTION_FAILED = "oms.action.failed"
    
    # 시스템 관련
    SYSTEM_STARTUP = "oms.system.startup"
    SYSTEM_SHUTDOWN = "oms.system.shutdown"

@dataclass
class OMSEvent:
    """OMS 이벤트 데이터 클래스"""
    event_id: str
    timestamp: str
    service: str = "oms"
    event_type: str = ""
    user_id: Optional[str] = None
    data: Dict[str, Any] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.data is None:
            self.data = {}
        if self.metadata is None:
            self.metadata = {}

class EventPublisher:
    """
    OMS 이벤트 퍼블리셔
    Audit Service로 이벤트를 발행하는 역할
    """
    
    def __init__(self, audit_service_url: str = "http://localhost:8002", timeout: int = 5):
        self.audit_service_url = audit_service_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        
    async def __aenter__(self):
        self._client = httpx.AsyncClient(
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
            raise RuntimeError("EventPublisher must be used as async context manager")
        return self._client
    
    def create_event(
        self, 
        event_type: EventType,
        data: Dict[str, Any],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> OMSEvent:
        """
        OMS 이벤트 생성
        
        Args:
            event_type: 이벤트 타입
            data: 이벤트 데이터
            user_id: 사용자 ID
            metadata: 추가 메타데이터
            
        Returns:
            OMSEvent: 생성된 이벤트 객체
        """
        return OMSEvent(
            event_id=str(uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type.value,
            user_id=user_id,
            data=data or {},
            metadata=metadata or {}
        )
    
    async def publish_event(self, event: OMSEvent) -> bool:
        """
        단일 이벤트 발행
        
        Args:
            event: 발행할 이벤트
            
        Returns:
            bool: 발행 성공 여부
        """
        try:
            response = await self.client.post(
                f"{self.audit_service_url}/api/v2/events",
                json=asdict(event)
            )
            return response.status_code in [200, 201, 202]
        except Exception as e:
            print(f"Failed to publish event {event.event_id}: {e}")
            return False
    
    async def publish_events(self, events: list[OMSEvent]) -> int:
        """
        배치 이벤트 발행
        
        Args:
            events: 발행할 이벤트 목록
            
        Returns:
            int: 성공적으로 발행된 이벤트 수
        """
        if not events:
            return 0
            
        try:
            response = await self.client.post(
                f"{self.audit_service_url}/api/v2/events/batch",
                json=[asdict(event) for event in events]
            )
            if response.status_code in [200, 201, 202]:
                return len(events)
        except Exception as e:
            print(f"Failed to publish batch events: {e}")
        
        # 배치 실패시 개별 발행 시도
        success_count = 0
        for event in events:
            if await self.publish_event(event):
                success_count += 1
        return success_count
    
    async def publish_schema_event(
        self,
        event_type: EventType,
        schema_id: str,
        schema_data: Dict[str, Any],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        스키마 관련 이벤트 발행
        
        Args:
            event_type: 이벤트 타입
            schema_id: 스키마 ID
            schema_data: 스키마 데이터
            user_id: 사용자 ID
            metadata: 추가 메타데이터
            
        Returns:
            bool: 발행 성공 여부
        """
        event_data = {
            "schema_id": schema_id,
            "schema_data": schema_data
        }
        
        event = self.create_event(
            event_type=event_type,
            data=event_data,
            user_id=user_id,
            metadata=metadata
        )
        
        return await self.publish_event(event)
    
    async def publish_branch_event(
        self,
        event_type: EventType,
        branch_name: str,
        branch_data: Dict[str, Any],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        브랜치 관련 이벤트 발행
        
        Args:
            event_type: 이벤트 타입
            branch_name: 브랜치 이름
            branch_data: 브랜치 데이터
            user_id: 사용자 ID
            metadata: 추가 메타데이터
            
        Returns:
            bool: 발행 성공 여부
        """
        event_data = {
            "branch_name": branch_name,
            "branch_data": branch_data
        }
        
        event = self.create_event(
            event_type=event_type,
            data=event_data,
            user_id=user_id,
            metadata=metadata
        )
        
        return await self.publish_event(event)
    
    async def publish_validation_event(
        self,
        event_type: EventType,
        validation_result: Dict[str, Any],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        검증 관련 이벤트 발행
        
        Args:
            event_type: 이벤트 타입
            validation_result: 검증 결과
            user_id: 사용자 ID
            metadata: 추가 메타데이터
            
        Returns:
            bool: 발행 성공 여부
        """
        event_data = {
            "validation_result": validation_result
        }
        
        event = self.create_event(
            event_type=event_type,
            data=event_data,
            user_id=user_id,
            metadata=metadata
        )
        
        return await self.publish_event(event)
    
    async def publish_action_event(
        self,
        event_type: EventType,
        action_name: str,
        action_result: Dict[str, Any],
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        액션 관련 이벤트 발행
        
        Args:
            event_type: 이벤트 타입
            action_name: 액션 이름
            action_result: 액션 결과
            user_id: 사용자 ID
            metadata: 추가 메타데이터
            
        Returns:
            bool: 발행 성공 여부
        """
        event_data = {
            "action_name": action_name,
            "action_result": action_result
        }
        
        event = self.create_event(
            event_type=event_type,
            data=event_data,
            user_id=user_id,
            metadata=metadata
        )
        
        return await self.publish_event(event)

# 싱글톤 퍼블리셔 인스턴스
_event_publisher: Optional[EventPublisher] = None

def get_event_publisher() -> EventPublisher:
    """Event Publisher 인스턴스 반환"""
    global _event_publisher
    if _event_publisher is None:
        _event_publisher = EventPublisher()
    return _event_publisher

# 편의 함수들
async def publish_schema_created(schema_id: str, schema_data: Dict[str, Any], user_id: Optional[str] = None):
    """스키마 생성 이벤트 발행 편의 함수"""
    async with get_event_publisher() as publisher:
        await publisher.publish_schema_event(
            EventType.SCHEMA_CREATED, schema_id, schema_data, user_id
        )

async def publish_schema_updated(schema_id: str, schema_data: Dict[str, Any], user_id: Optional[str] = None):
    """스키마 수정 이벤트 발행 편의 함수"""
    async with get_event_publisher() as publisher:
        await publisher.publish_schema_event(
            EventType.SCHEMA_UPDATED, schema_id, schema_data, user_id
        )

async def publish_branch_created(branch_name: str, branch_data: Dict[str, Any], user_id: Optional[str] = None):
    """브랜치 생성 이벤트 발행 편의 함수"""
    async with get_event_publisher() as publisher:
        await publisher.publish_branch_event(
            EventType.BRANCH_CREATED, branch_name, branch_data, user_id
        )

async def publish_validation_failed(validation_result: Dict[str, Any], user_id: Optional[str] = None):
    """검증 실패 이벤트 발행 편의 함수"""
    async with get_event_publisher() as publisher:
        await publisher.publish_validation_event(
            EventType.VALIDATION_FAILED, validation_result, user_id
        )

async def publish_action_executed(action_name: str, action_result: Dict[str, Any], user_id: Optional[str] = None):
    """액션 실행 이벤트 발행 편의 함수"""
    async with get_event_publisher() as publisher:
        await publisher.publish_action_event(
            EventType.ACTION_EXECUTED, action_name, action_result, user_id
        )