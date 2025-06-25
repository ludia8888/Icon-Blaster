"""
Audit Log Models (Migrated from OMS)
OMS core/history/models.py에서 이관된 감사 로그 모델들
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class AuditEventType(str, Enum):
    """감사 이벤트 타입"""
    SCHEMA_CHANGE = "schema_change"
    SCHEMA_REVERT = "schema_revert" 
    SCHEMA_VALIDATION = "schema_validation"
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    PERMISSION_CHANGE = "permission_change"
    DATA_ACCESS = "data_access"
    API_ACCESS = "api_access"
    SYSTEM_ERROR = "system_error"


class SeverityLevel(str, Enum):
    """심각도 레벨"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditLogEntry(BaseModel):
    """
    중앙 SIEM 전송용 감사 로그 포맷 (OMS에서 이관)
    """
    # 기본 감사 정보
    log_id: str = Field(description="로그 고유 식별자")
    timestamp: datetime = Field(description="이벤트 발생 시각 (UTC)")
    service: str = Field(default="oms", description="서비스 식별자")
    event_type: AuditEventType = Field(description="이벤트 타입")
    severity: SeverityLevel = Field(default=SeverityLevel.INFO, description="심각도")
    
    # 사용자 정보
    user_id: str = Field(description="사용자 ID")
    user_email: Optional[str] = Field(None, description="사용자 이메일")
    user_role: Optional[str] = Field(None, description="사용자 역할")
    impersonated_by: Optional[str] = Field(None, description="대행 사용자 ID")
    
    # 액션 정보
    action: str = Field(description="수행된 액션")
    resource_type: str = Field(description="대상 리소스 타입")
    resource_id: str = Field(description="대상 리소스 ID")
    resource_name: Optional[str] = Field(None, description="리소스 이름")
    result: str = Field(default="success", description="실행 결과 (success/failure/partial)")
    
    # 네트워크/세션 정보
    ip_address: Optional[str] = Field(None, description="클라이언트 IP 주소")
    user_agent: Optional[str] = Field(None, description="User Agent")
    session_id: Optional[str] = Field(None, description="세션 ID")
    request_id: Optional[str] = Field(None, description="요청 ID")
    
    # 규제 준수 필드
    data_classification: Optional[str] = Field(None, description="데이터 분류 (public/internal/confidential/restricted)")
    compliance_tags: List[str] = Field(default_factory=list, description="규제 준수 태그 (SOX, GDPR, HIPAA 등)")
    retention_days: int = Field(2555, description="보관 기간 (일, 기본 7년)")
    legal_hold: bool = Field(False, description="법적 보존 대상 여부")
    
    # 상세 정보
    details: Dict[str, Any] = Field(default_factory=dict, description="상세 정보")
    before_state: Optional[Dict[str, Any]] = Field(None, description="변경 전 상태")
    after_state: Optional[Dict[str, Any]] = Field(None, description="변경 후 상태")
    
    # 메타데이터
    correlation_id: Optional[str] = Field(None, description="연관 이벤트 ID")
    transaction_id: Optional[str] = Field(None, description="트랜잭션 ID")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")
    
    # 성능/크기 정보
    processing_time_ms: Optional[int] = Field(None, description="처리 시간 (밀리초)")
    payload_size_bytes: Optional[int] = Field(None, description="페이로드 크기 (바이트)")
    
    @field_validator('retention_days')
    def validate_retention_days(cls, v):
        if v < 1:
            raise ValueError("retention_days must be at least 1")
        return v
    
    @field_validator('result')
    def validate_result(cls, v):
        allowed = ['success', 'failure', 'partial', 'timeout', 'cancelled']
        if v not in allowed:
            raise ValueError(f"result must be one of {allowed}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "log_id": "audit_abc123def456",
                "timestamp": "2025-06-25T10:30:00Z",
                "service": "oms",
                "event_type": "schema_change",
                "severity": "info",
                "user_id": "user123",
                "user_email": "user@company.com",
                "action": "update_object_type",
                "resource_type": "ObjectType",
                "resource_id": "obj_Product",
                "result": "success",
                "ip_address": "192.168.1.100",
                "compliance_tags": ["SOX", "PCI-DSS"],
                "retention_days": 2555
            }
        }


class AuditSearchQuery(BaseModel):
    """감사 로그 검색 쿼리"""
    # 시간 범위
    from_date: Optional[datetime] = Field(None, description="시작 날짜")
    to_date: Optional[datetime] = Field(None, description="종료 날짜")
    
    # 필터링
    user_id: Optional[str] = Field(None, description="사용자 ID 필터")
    event_type: Optional[AuditEventType] = Field(None, description="이벤트 타입 필터")
    severity: Optional[SeverityLevel] = Field(None, description="심각도 필터")
    service: Optional[str] = Field(None, description="서비스 필터")
    action: Optional[str] = Field(None, description="액션 필터")
    resource_type: Optional[str] = Field(None, description="리소스 타입 필터")
    resource_id: Optional[str] = Field(None, description="리소스 ID 필터")
    result: Optional[str] = Field(None, description="결과 필터")
    ip_address: Optional[str] = Field(None, description="IP 주소 필터")
    
    # 규제 준수 필터
    compliance_tags: Optional[List[str]] = Field(None, description="규제 준수 태그 필터")
    data_classification: Optional[str] = Field(None, description="데이터 분류 필터")
    legal_hold: Optional[bool] = Field(None, description="법적 보존 대상 필터")
    
    # 검색
    search_text: Optional[str] = Field(None, description="텍스트 검색 (action, resource_id, details)")
    correlation_id: Optional[str] = Field(None, description="연관 이벤트 ID")
    transaction_id: Optional[str] = Field(None, description="트랜잭션 ID")
    
    # 페이지네이션
    limit: int = Field(100, ge=1, le=10000, description="결과 제한")
    offset: int = Field(0, ge=0, description="결과 시작 위치")
    cursor: Optional[str] = Field(None, description="커서 기반 페이지네이션")
    
    # 정렬
    sort_by: str = Field("timestamp", description="정렬 기준")
    sort_order: str = Field("desc", description="정렬 순서 (asc/desc)")
    
    # 집계 옵션
    include_aggregations: bool = Field(False, description="집계 정보 포함 여부")
    aggregation_fields: Optional[List[str]] = Field(None, description="집계할 필드 목록")
    
    @field_validator('sort_by')
    def validate_sort_by(cls, v):
        allowed = ['timestamp', 'user_id', 'event_type', 'severity', 'action', 'resource_type']
        if v not in allowed:
            raise ValueError(f"sort_by must be one of {allowed}")
        return v
    
    @field_validator('sort_order')
    def validate_sort_order(cls, v):
        if v not in ['asc', 'desc']:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v


class AuditSearchResponse(BaseModel):
    """감사 로그 검색 응답"""
    # 결과 데이터
    entries: List[AuditLogEntry] = Field(description="감사 로그 엔트리 목록")
    
    # 페이지네이션 정보
    total_count: int = Field(description="전체 결과 개수")
    has_more: bool = Field(description="추가 결과 여부")
    next_cursor: Optional[str] = Field(None, description="다음 페이지 커서")
    
    # 쿼리 정보
    query_time_ms: int = Field(description="쿼리 실행 시간 (밀리초)")
    applied_filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="적용된 필터 정보"
    )
    
    # 집계 정보
    aggregations: Optional[Dict[str, Any]] = Field(None, description="집계 결과")
    
    # 통계 정보
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="결과 요약 통계"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "entries": [],
                "total_count": 1250,
                "has_more": True,
                "next_cursor": "eyJ0aW1lc3RhbXAiOiIyMDI1LTA2LTI1VDEwOjMwOjAwWiJ9",
                "query_time_ms": 89,
                "summary": {
                    "event_types": {"schema_change": 800, "user_login": 300, "api_access": 150},
                    "severity_levels": {"info": 1000, "warning": 200, "error": 50},
                    "success_rate": 0.96,
                    "unique_users": 45,
                    "time_range_hours": 24
                },
                "aggregations": {
                    "by_hour": [
                        {"hour": "2025-06-25T10:00:00Z", "count": 120},
                        {"hour": "2025-06-25T11:00:00Z", "count": 95}
                    ],
                    "top_users": [
                        {"user_id": "user123", "count": 45},
                        {"user_id": "user456", "count": 32}
                    ]
                }
            }
        }


class AuditExportRequest(BaseModel):
    """감사 로그 내보내기 요청"""
    # 내보내기 범위
    query: AuditSearchQuery = Field(description="내보낼 데이터 쿼리")
    
    # 내보내기 형식
    format: str = Field("json", description="내보내기 형식 (json/csv/xlsx/pdf)")
    compression: Optional[str] = Field(None, description="압축 형식 (zip/gzip)")
    
    # 포함 옵션
    include_metadata: bool = Field(True, description="메타데이터 포함 여부")
    include_details: bool = Field(True, description="상세 정보 포함 여부")
    include_states: bool = Field(False, description="before/after 상태 포함 여부")
    
    # 규제 준수 옵션
    redact_pii: bool = Field(True, description="개인정보 마스킹 여부")
    redact_fields: Optional[List[str]] = Field(None, description="마스킹할 필드 목록")
    audit_purpose: str = Field(description="감사 목적 (compliance/investigation/analysis)")
    requestor_id: str = Field(description="요청자 ID")
    
    # 배달 옵션
    delivery_method: str = Field("download", description="배달 방식 (download/email/s3)")
    delivery_config: Optional[Dict[str, Any]] = Field(None, description="배달 설정")
    
    @field_validator('format')
    def validate_format(cls, v):
        allowed = ['json', 'csv', 'xlsx', 'pdf', 'parquet']
        if v not in allowed:
            raise ValueError(f"format must be one of {allowed}")
        return v
    
    @field_validator('delivery_method')
    def validate_delivery_method(cls, v):
        allowed = ['download', 'email', 's3', 'sftp']
        if v not in allowed:
            raise ValueError(f"delivery_method must be one of {allowed}")
        return v


class AuditExportResponse(BaseModel):
    """감사 로그 내보내기 응답"""
    export_id: str = Field(description="내보내기 작업 ID")
    status: str = Field(description="작업 상태 (pending/processing/completed/failed)")
    created_at: datetime = Field(description="요청 시각")
    
    # 진행 정보
    total_records: Optional[int] = Field(None, description="총 레코드 수")
    processed_records: Optional[int] = Field(None, description="처리된 레코드 수")
    progress_percentage: Optional[float] = Field(None, description="진행률 (%)")
    estimated_completion: Optional[datetime] = Field(None, description="예상 완료 시각")
    
    # 결과 정보
    download_url: Optional[str] = Field(None, description="다운로드 URL")
    file_size_bytes: Optional[int] = Field(None, description="파일 크기 (바이트)")
    expires_at: Optional[datetime] = Field(None, description="만료 시각")
    
    # 에러 정보
    error_message: Optional[str] = Field(None, description="에러 메시지")
    error_code: Optional[str] = Field(None, description="에러 코드")
    
    class Config:
        json_schema_extra = {
            "example": {
                "export_id": "export_abc123",
                "status": "completed",
                "created_at": "2025-06-25T10:30:00Z",
                "total_records": 1250,
                "processed_records": 1250,
                "progress_percentage": 100.0,
                "download_url": "https://audit-service.com/exports/export_abc123/download",
                "file_size_bytes": 2048576,
                "expires_at": "2025-06-26T10:30:00Z"
            }
        }