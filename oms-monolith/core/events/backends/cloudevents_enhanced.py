"""
Enhanced CloudEvents Implementation
CloudEvents 1.0 표준 완전 준수 및 확장 기능 구현
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

from pydantic import BaseModel, Field, field_validator, ConfigDict


class ContentMode(str, Enum):
    """CloudEvents 컨텐츠 모드"""
    STRUCTURED = "structured"  # 모든 데이터가 payload에 포함
    BINARY = "binary"         # 메타데이터는 헤더에, 데이터는 payload에


class CloudEventSpec(str, Enum):
    """지원되는 CloudEvents 스펙 버전"""
    V1_0 = "1.0"


class EventType(str, Enum):
    """OMS 이벤트 타입 정의"""
    # Schema 관련 이벤트
    SCHEMA_CREATED = "com.foundry.oms.schema.created"
    SCHEMA_UPDATED = "com.foundry.oms.schema.updated"
    SCHEMA_DELETED = "com.foundry.oms.schema.deleted"
    SCHEMA_VALIDATED = "com.foundry.oms.schema.validated"
    
    # ObjectType 이벤트
    OBJECT_TYPE_CREATED = "com.foundry.oms.objecttype.created"
    OBJECT_TYPE_UPDATED = "com.foundry.oms.objecttype.updated"
    OBJECT_TYPE_DELETED = "com.foundry.oms.objecttype.deleted"
    
    # Property 이벤트
    PROPERTY_CREATED = "com.foundry.oms.property.created"
    PROPERTY_UPDATED = "com.foundry.oms.property.updated"
    PROPERTY_DELETED = "com.foundry.oms.property.deleted"
    
    # LinkType 이벤트
    LINK_TYPE_CREATED = "com.foundry.oms.linktype.created"
    LINK_TYPE_UPDATED = "com.foundry.oms.linktype.updated"
    LINK_TYPE_DELETED = "com.foundry.oms.linktype.deleted"
    
    # Branch 관련 이벤트
    BRANCH_CREATED = "com.foundry.oms.branch.created"
    BRANCH_UPDATED = "com.foundry.oms.branch.updated"
    BRANCH_DELETED = "com.foundry.oms.branch.deleted"
    BRANCH_MERGED = "com.foundry.oms.branch.merged"
    
    # Proposal 이벤트
    PROPOSAL_CREATED = "com.foundry.oms.proposal.created"
    PROPOSAL_UPDATED = "com.foundry.oms.proposal.updated"
    PROPOSAL_APPROVED = "com.foundry.oms.proposal.approved"
    PROPOSAL_REJECTED = "com.foundry.oms.proposal.rejected"
    PROPOSAL_MERGED = "com.foundry.oms.proposal.merged"
    
    # Action 이벤트
    ACTION_STARTED = "com.foundry.oms.action.started"
    ACTION_COMPLETED = "com.foundry.oms.action.completed"
    ACTION_FAILED = "com.foundry.oms.action.failed"
    ACTION_CANCELLED = "com.foundry.oms.action.cancelled"
    
    # System 이벤트
    SYSTEM_HEALTH_CHECK = "com.foundry.oms.system.healthcheck"
    SYSTEM_ERROR = "com.foundry.oms.system.error"
    SYSTEM_MAINTENANCE = "com.foundry.oms.system.maintenance"


class CloudEventContext(BaseModel):
    """CloudEvents 컨텍스트 속성 (메타데이터)"""
    model_config = ConfigDict(extra='allow')  # 확장 속성 허용
    
    # 필수 속성
    specversion: CloudEventSpec = CloudEventSpec.V1_0
    type: Union[EventType, str]
    source: str
    id: str
    
    # 선택적 속성
    time: Optional[datetime] = None
    datacontenttype: str = "application/json"
    dataschema: Optional[str] = None
    subject: Optional[str] = None
    
    @field_validator('id')
    @classmethod
    def validate_id(cls, v):
        """ID는 UUID 형식이거나 유효한 문자열이어야 함"""
        if not v:
            raise ValueError("Event ID cannot be empty")
        return v
    
    @field_validator('source')
    @classmethod
    def validate_source(cls, v):
        """Source는 URI 형식이어야 함"""
        if not v.startswith(('/', 'http://', 'https://', 'urn:')):
            raise ValueError("Source must be a valid URI")
        return v
    
    @field_validator('time', mode='before')
    @classmethod
    def ensure_timezone(cls, v):
        """시간대 정보가 없으면 UTC로 설정"""
        if v and isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class EnhancedCloudEvent(BaseModel):
    """향상된 CloudEvents 구현체"""
    model_config = ConfigDict(extra='allow')
    
    # CloudEvents 표준 속성
    specversion: CloudEventSpec = CloudEventSpec.V1_0
    type: Union[EventType, str]
    source: str
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    datacontenttype: str = "application/json"
    dataschema: Optional[str] = None
    subject: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    
    # OMS 확장 속성 (ce- prefix)
    ce_correlationid: Optional[str] = None      # 연관 이벤트 추적
    ce_causationid: Optional[str] = None        # 인과관계 추적
    ce_sequencenumber: Optional[int] = None     # 이벤트 순서
    ce_partition: Optional[str] = None          # 파티셔닝 키
    ce_traceparent: Optional[str] = None        # 분산 추적
    ce_spanid: Optional[str] = None             # 스팬 ID
    
    # OMS 도메인 특화 속성
    ce_branch: Optional[str] = None             # Git 브랜치
    ce_commit: Optional[str] = None             # 커밋 ID
    ce_author: Optional[str] = None             # 작성자
    ce_tenant: Optional[str] = None             # 테넌트 ID
    ce_workspace: Optional[str] = None          # 워크스페이스
    ce_resourceversion: Optional[str] = None    # 리소스 버전
    
    def to_structured_format(self) -> Dict[str, Any]:
        """Structured Content Mode 형식으로 변환"""
        return self.model_dump(exclude_none=True)
    
    def to_binary_headers(self) -> Dict[str, str]:
        """Binary Content Mode용 헤더 생성"""
        headers = {}
        
        # 표준 속성을 HTTP 헤더로 변환
        headers['ce-specversion'] = self.specversion
        headers['ce-type'] = str(self.type)
        headers['ce-source'] = self.source
        headers['ce-id'] = self.id
        
        if self.time:
            headers['ce-time'] = self.time.isoformat()
        if self.datacontenttype:
            headers['content-type'] = self.datacontenttype
        if self.dataschema:
            headers['ce-dataschema'] = self.dataschema
        if self.subject:
            headers['ce-subject'] = self.subject
            
        # 확장 속성 추가
        for field_name, value in self.model_dump(exclude_none=True).items():
            if field_name.startswith('ce_') and value is not None:
                header_name = field_name.replace('_', '-')
                headers[header_name] = str(value)
        
        return headers
    
    def get_nats_subject(self) -> str:
        """NATS JetStream subject 생성"""
        # Event type에서 subject 생성
        if isinstance(self.type, EventType):
            type_parts = self.type.value.split('.')
            # com.foundry.oms.schema.created -> oms.schema.created
            if len(type_parts) >= 4:
                return '.'.join(type_parts[2:])
        
        # fallback
        return f"oms.{self.type}"
    
    def add_trace_context(self, trace_parent: str, span_id: str) -> None:
        """분산 추적 컨텍스트 추가"""
        self.ce_traceparent = trace_parent
        self.ce_spanid = span_id
    
    def add_correlation_context(self, correlation_id: str, causation_id: Optional[str] = None) -> None:
        """연관관계 컨텍스트 추가"""
        self.ce_correlationid = correlation_id
        if causation_id:
            self.ce_causationid = causation_id
    
    def add_oms_context(self, branch: str, commit: str, author: str, tenant: Optional[str] = None) -> None:
        """OMS 도메인 컨텍스트 추가"""
        self.ce_branch = branch
        self.ce_commit = commit
        self.ce_author = author
        if tenant:
            self.ce_tenant = tenant
    
    @classmethod
    def from_legacy_event(cls, legacy_event: Dict[str, Any]) -> "EnhancedCloudEvent":
        """기존 이벤트 형식에서 변환"""
        # 기존 이벤트 구조 파싱
        event_type = legacy_event.get('type', 'com.foundry.oms.unknown')
        source = legacy_event.get('source', '/oms')
        
        # CloudEvent 생성
        cloud_event = cls(
            type=event_type,
            source=source,
            data=legacy_event.get('data', {}),
            subject=legacy_event.get('subject')
        )
        
        # 메타데이터 매핑
        if 'metadata' in legacy_event:
            metadata = legacy_event['metadata']
            cloud_event.add_oms_context(
                branch=metadata.get('branch', 'main'),
                commit=metadata.get('commit_id', ''),
                author=metadata.get('author', 'unknown')
            )
        
        return cloud_event


class CloudEventBuilder:
    """CloudEvent 빌더 패턴"""
    
    def __init__(self, event_type: Union[EventType, str], source: str):
        self._event = EnhancedCloudEvent(type=event_type, source=source)
    
    def with_id(self, event_id: str) -> "CloudEventBuilder":
        self._event.id = event_id
        return self
    
    def with_subject(self, subject: str) -> "CloudEventBuilder":
        self._event.subject = subject
        return self
    
    def with_data(self, data: Dict[str, Any]) -> "CloudEventBuilder":
        self._event.data = data
        return self
    
    def with_schema(self, schema_uri: str) -> "CloudEventBuilder":
        self._event.dataschema = schema_uri
        return self
    
    def with_correlation(self, correlation_id: str, causation_id: Optional[str] = None) -> "CloudEventBuilder":
        self._event.add_correlation_context(correlation_id, causation_id)
        return self
    
    def with_oms_context(self, branch: str, commit: str, author: str, tenant: Optional[str] = None) -> "CloudEventBuilder":
        self._event.add_oms_context(branch, commit, author, tenant)
        return self
    
    def with_trace(self, trace_parent: str, span_id: str) -> "CloudEventBuilder":
        self._event.add_trace_context(trace_parent, span_id)
        return self
    
    def build(self) -> EnhancedCloudEvent:
        return self._event


class CloudEventValidator:
    """CloudEvent 유효성 검증기"""
    
    @staticmethod
    def validate_cloudevent(event: EnhancedCloudEvent) -> List[str]:
        """CloudEvent 유효성 검증"""
        errors = []
        
        # 필수 필드 검증
        if not event.specversion:
            errors.append("specversion is required")
        elif event.specversion != CloudEventSpec.V1_0:
            errors.append(f"Unsupported specversion: {event.specversion}")
        
        if not event.type:
            errors.append("type is required")
        
        if not event.source:
            errors.append("source is required")
        
        if not event.id:
            errors.append("id is required")
        
        # 타입별 특화 검증
        if isinstance(event.type, str):
            if not event.type.startswith('com.'):
                errors.append("Event type should follow reverse domain notation")
        
        # 확장 속성 검증
        if event.ce_sequencenumber is not None and event.ce_sequencenumber < 0:
            errors.append("Sequence number must be non-negative")
        
        return errors
    
    @staticmethod
    def is_valid_cloudevent(event: EnhancedCloudEvent) -> bool:
        """CloudEvent가 유효한지 확인"""
        return len(CloudEventValidator.validate_cloudevent(event)) == 0


# 편의 함수들
def create_schema_event(operation: str, resource_type: str, resource_id: str, 
                       branch: str, commit: str, author: str,
                       old_value: Any = None, new_value: Any = None) -> EnhancedCloudEvent:
    """스키마 변경 이벤트 생성"""
    event_type_map = {
        'create': EventType.SCHEMA_CREATED,
        'update': EventType.SCHEMA_UPDATED,
        'delete': EventType.SCHEMA_DELETED
    }
    
    event_type = event_type_map.get(operation, EventType.SCHEMA_UPDATED)
    
    return CloudEventBuilder(event_type, f"/oms/{branch}") \
        .with_subject(f"{resource_type}/{resource_id}") \
        .with_data({
            "operation": operation,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "old_value": old_value,
            "new_value": new_value
        }) \
        .with_oms_context(branch, commit, author) \
        .build()


def create_action_event(action_type: str, job_id: str, status: str,
                       result: Optional[Dict[str, Any]] = None,
                       error: Optional[str] = None) -> EnhancedCloudEvent:
    """액션 이벤트 생성"""
    status_event_map = {
        'started': EventType.ACTION_STARTED,
        'completed': EventType.ACTION_COMPLETED,
        'failed': EventType.ACTION_FAILED,
        'cancelled': EventType.ACTION_CANCELLED
    }
    
    event_type = status_event_map.get(status, EventType.ACTION_STARTED)
    
    data = {
        "action_type": action_type,
        "job_id": job_id,
        "status": status
    }
    
    if result:
        data["result"] = result
    if error:
        data["error"] = error
    
    return CloudEventBuilder(event_type, "/oms/actions") \
        .with_subject(job_id) \
        .with_data(data) \
        .build()