"""
SIEM Integration Models
중앙 SIEM 시스템 연동을 위한 모델들
"""
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class SiemProvider(str, Enum):
    """SIEM 제공업체"""
    SPLUNK = "splunk"
    ELASTIC = "elastic"
    QRADAR = "qradar"
    ARCSIGHT = "arcsight"
    SENTINEL = "sentinel"
    CHRONICLE = "chronicle"
    SUMOLOGIC = "sumologic"
    DATADOG = "datadog"


class SiemEventFormat(str, Enum):
    """SIEM 이벤트 형식"""
    CEF = "cef"  # Common Event Format
    LEEF = "leef"  # Log Event Extended Format
    JSON = "json"
    SYSLOG = "syslog"
    STIX = "stix"  # Structured Threat Information eXpression


class SiemLogEntry(BaseModel):
    """SIEM 전송용 로그 엔트리"""
    # SIEM 기본 필드
    timestamp: datetime = Field(description="이벤트 시각 (UTC)")
    source_system: str = Field(default="audit-service", description="소스 시스템")
    event_id: str = Field(description="이벤트 고유 ID")
    event_type: str = Field(description="이벤트 타입")
    
    # CEF 필수 필드
    device_vendor: str = Field(default="OMS", description="장치 벤더")
    device_product: str = Field(default="Audit-Service", description="장치 제품")
    device_version: str = Field(default="1.0", description="장치 버전")
    signature_id: str = Field(description="시그니처 ID")
    severity: int = Field(ge=0, le=10, description="심각도 (0-10)")
    
    # 확장 필드
    source_ip: Optional[str] = Field(None, description="소스 IP")
    destination_ip: Optional[str] = Field(None, description="대상 IP")
    source_user: Optional[str] = Field(None, description="소스 사용자")
    destination_user: Optional[str] = Field(None, description="대상 사용자")
    source_process: Optional[str] = Field(None, description="소스 프로세스")
    file_name: Optional[str] = Field(None, description="파일명")
    request_url: Optional[str] = Field(None, description="요청 URL")
    request_method: Optional[str] = Field(None, description="요청 메소드")
    
    # 사용자 정의 확장
    custom_fields: Dict[str, Any] = Field(default_factory=dict, description="사용자 정의 필드")
    
    # 메타데이터
    correlation_id: Optional[str] = Field(None, description="연관 ID")
    raw_event: Optional[str] = Field(None, description="원본 이벤트")
    
    @field_validator('severity')
    def validate_severity(cls, v):
        # CEF 심각도 매핑
        # 0-3: Low, 4-6: Medium, 7-8: High, 9-10: Very High
        return v
    
    def to_cef(self) -> str:
        """CEF 형식으로 변환"""
        # CEF:Version|Device Vendor|Device Product|Device Version|Signature ID|Name|Severity|Extension
        header = f"CEF:0|{self.device_vendor}|{self.device_product}|{self.device_version}|{self.signature_id}|{self.event_type}|{self.severity}"
        
        extensions = []
        if self.source_ip:
            extensions.append(f"src={self.source_ip}")
        if self.destination_ip:
            extensions.append(f"dst={self.destination_ip}")
        if self.source_user:
            extensions.append(f"suser={self.source_user}")
        if self.destination_user:
            extensions.append(f"duser={self.destination_user}")
        if self.request_url:
            extensions.append(f"request={self.request_url}")
        if self.request_method:
            extensions.append(f"requestMethod={self.request_method}")
        
        # 사용자 정의 필드 추가
        for key, value in self.custom_fields.items():
            extensions.append(f"cs1Label={key} cs1={value}")
        
        extension_str = " ".join(extensions)
        return f"{header}|{extension_str}"
    
    def to_leef(self) -> str:
        """LEEF 형식으로 변환"""
        # LEEF:Version|Vendor|Product|Version|EventID|Fields
        header = f"LEEF:2.0|{self.device_vendor}|{self.device_product}|{self.device_version}|{self.signature_id}"
        
        fields = [
            f"devTime={int(self.timestamp.timestamp() * 1000)}",
            f"eventId={self.event_id}",
            f"severity={self.severity}"
        ]
        
        if self.source_ip:
            fields.append(f"srcIP={self.source_ip}")
        if self.source_user:
            fields.append(f"srcUser={self.source_user}")
        
        # 탭으로 구분
        fields_str = "\t".join(fields)
        return f"{header}\t{fields_str}"


class SiemConfig(BaseModel):
    """SIEM 연동 설정"""
    # 기본 설정
    provider: SiemProvider = Field(description="SIEM 제공업체")
    enabled: bool = Field(default=True, description="연동 활성화 여부")
    format: SiemEventFormat = Field(default=SiemEventFormat.JSON, description="이벤트 형식")
    
    # 연결 설정
    endpoint_url: str = Field(description="SIEM 엔드포인트 URL")
    auth_method: str = Field(description="인증 방식 (api_key/basic/oauth2/certificate)")
    auth_config: Dict[str, Any] = Field(description="인증 설정")
    
    # 전송 설정
    batch_size: int = Field(default=100, ge=1, le=10000, description="배치 크기")
    batch_timeout_seconds: int = Field(default=30, ge=1, le=300, description="배치 타임아웃")
    retry_count: int = Field(default=3, ge=0, le=10, description="재시도 횟수")
    retry_delay_seconds: int = Field(default=5, ge=1, le=60, description="재시도 지연")
    
    # 필터링 설정
    severity_threshold: int = Field(default=0, ge=0, le=10, description="최소 심각도")
    event_types: Optional[List[str]] = Field(None, description="전송할 이벤트 타입 (None=모든 타입)")
    exclude_fields: List[str] = Field(default_factory=list, description="제외할 필드")
    
    # 보안 설정
    enable_tls: bool = Field(default=True, description="TLS 활성화")
    verify_ssl: bool = Field(default=True, description="SSL 검증")
    client_cert_path: Optional[str] = Field(None, description="클라이언트 인증서 경로")
    client_key_path: Optional[str] = Field(None, description="클라이언트 키 경로")
    
    # 매핑 설정
    field_mappings: Dict[str, str] = Field(
        default_factory=dict, 
        description="필드 매핑 (source_field: target_field)"
    )
    
    @field_validator('auth_method')
    def validate_auth_method(cls, v):
        allowed = ['api_key', 'basic', 'oauth2', 'certificate', 'none']
        if v not in allowed:
            raise ValueError(f"auth_method must be one of {allowed}")
        return v


class SiemTransmissionStatus(BaseModel):
    """SIEM 전송 상태"""
    transmission_id: str = Field(description="전송 ID")
    timestamp: datetime = Field(description="전송 시각")
    status: str = Field(description="전송 상태 (pending/success/failed/retry)")
    
    # 배치 정보
    batch_size: int = Field(description="배치 크기")
    events_count: int = Field(description="이벤트 수")
    
    # 결과 정보
    success_count: int = Field(default=0, description="성공한 이벤트 수")
    failed_count: int = Field(default=0, description="실패한 이벤트 수")
    
    # 성능 정보
    transmission_time_ms: Optional[int] = Field(None, description="전송 시간 (밀리초)")
    response_time_ms: Optional[int] = Field(None, description="응답 시간 (밀리초)")
    
    # 에러 정보
    error_message: Optional[str] = Field(None, description="에러 메시지")
    error_code: Optional[str] = Field(None, description="에러 코드")
    retry_count: int = Field(default=0, description="재시도 횟수")
    
    # SIEM 응답
    siem_response: Optional[Dict[str, Any]] = Field(None, description="SIEM 응답")
    acknowledgment_id: Optional[str] = Field(None, description="SIEM 확인 ID")


class SiemHealthCheck(BaseModel):
    """SIEM 연결 상태 체크"""
    provider: SiemProvider = Field(description="SIEM 제공업체")
    endpoint_url: str = Field(description="엔드포인트 URL")
    
    # 상태 정보
    is_healthy: bool = Field(description="연결 상태")
    last_check_time: datetime = Field(description="마지막 체크 시각")
    response_time_ms: Optional[int] = Field(None, description="응답 시간 (밀리초)")
    
    # 통계 정보
    total_events_sent: int = Field(default=0, description="총 전송 이벤트 수")
    success_rate: float = Field(default=0.0, description="성공률 (0-1)")
    average_response_time_ms: float = Field(default=0.0, description="평균 응답 시간")
    
    # 최근 에러
    last_error: Optional[str] = Field(None, description="마지막 에러")
    last_error_time: Optional[datetime] = Field(None, description="마지막 에러 시각")
    consecutive_failures: int = Field(default=0, description="연속 실패 횟수")
    
    # 버전 정보
    siem_version: Optional[str] = Field(None, description="SIEM 버전")
    api_version: Optional[str] = Field(None, description="API 버전")


class SiemMetrics(BaseModel):
    """SIEM 연동 메트릭스"""
    time_range_start: datetime = Field(description="시간 범위 시작")
    time_range_end: datetime = Field(description="시간 범위 종료")
    
    # 전송 통계
    total_events: int = Field(description="총 이벤트 수")
    successful_transmissions: int = Field(description="성공한 전송 수")
    failed_transmissions: int = Field(description="실패한 전송 수")
    retried_transmissions: int = Field(description="재시도한 전송 수")
    
    # 성능 통계
    average_batch_size: float = Field(description="평균 배치 크기")
    average_transmission_time_ms: float = Field(description="평균 전송 시간")
    average_response_time_ms: float = Field(description="평균 응답 시간")
    throughput_events_per_second: float = Field(description="처리량 (이벤트/초)")
    
    # 에러 통계
    error_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="에러 유형별 분포"
    )
    
    # 품질 지표
    success_rate: float = Field(description="성공률 (0-1)")
    availability: float = Field(description="가용성 (0-1)")
    data_integrity: float = Field(description="데이터 무결성 (0-1)")