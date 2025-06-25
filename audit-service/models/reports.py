"""
Audit Report Models
규제 준수 및 감사 리포트 모델들
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ComplianceStandard(str, Enum):
    """규제 준수 표준"""
    SOX = "sox"  # Sarbanes-Oxley Act
    GDPR = "gdpr"  # General Data Protection Regulation
    HIPAA = "hipaa"  # Health Insurance Portability and Accountability Act
    PCI_DSS = "pci_dss"  # Payment Card Industry Data Security Standard
    ISO_27001 = "iso_27001"  # Information Security Management
    NIST = "nist"  # National Institute of Standards and Technology
    COBIT = "cobit"  # Control Objectives for Information and Related Technologies
    ITIL = "itil"  # Information Technology Infrastructure Library


class ReportType(str, Enum):
    """리포트 타입"""
    COMPLIANCE = "compliance"  # 규제 준수 리포트
    AUDIT_TRAIL = "audit_trail"  # 감사 추적 리포트
    ACCESS_REPORT = "access_report"  # 접근 리포트
    CHANGE_REPORT = "change_report"  # 변경 리포트
    SECURITY_REPORT = "security_report"  # 보안 리포트
    PERFORMANCE_REPORT = "performance_report"  # 성능 리포트
    EXECUTIVE_SUMMARY = "executive_summary"  # 경영진 요약


class ReportStatus(str, Enum):
    """리포트 상태"""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class ComplianceReport(BaseModel):
    """규제 준수 리포트"""
    # 기본 정보
    report_id: str = Field(description="리포트 ID")
    report_type: ReportType = Field(description="리포트 타입")
    compliance_standard: ComplianceStandard = Field(description="준수 표준")
    title: str = Field(description="리포트 제목")
    description: Optional[str] = Field(None, description="리포트 설명")
    
    # 생성 정보
    generated_by: str = Field(description="생성자 ID")
    generated_at: datetime = Field(description="생성 시각")
    period_start: datetime = Field(description="리포트 기간 시작")
    period_end: datetime = Field(description="리포트 기간 종료")
    
    # 상태 정보
    status: ReportStatus = Field(description="리포트 상태")
    generation_time_ms: Optional[int] = Field(None, description="생성 시간 (밀리초)")
    
    # 요약 통계
    total_events: int = Field(description="총 이벤트 수")
    compliant_events: int = Field(description="준수 이벤트 수")
    non_compliant_events: int = Field(description="비준수 이벤트 수")
    compliance_score: float = Field(ge=0.0, le=1.0, description="준수 점수 (0-1)")
    
    # 위험 평가
    risk_level: str = Field(description="위험 수준 (low/medium/high/critical)")
    critical_findings: int = Field(description="심각한 발견사항 수")
    high_findings: int = Field(description="높은 위험 발견사항 수")
    medium_findings: int = Field(description="중간 위험 발견사항 수")
    low_findings: int = Field(description="낮은 위험 발견사항 수")
    
    # 상세 결과
    findings: List['ComplianceFinding'] = Field(default_factory=list, description="발견사항 목록")
    recommendations: List['ComplianceRecommendation'] = Field(default_factory=list, description="권고사항 목록")
    
    # 파일 정보
    file_path: Optional[str] = Field(None, description="생성된 파일 경로")
    file_size_bytes: Optional[int] = Field(None, description="파일 크기")
    download_url: Optional[str] = Field(None, description="다운로드 URL")
    expires_at: Optional[datetime] = Field(None, description="만료 시각")
    
    # 메타데이터
    metadata: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")
    
    @field_validator('compliance_score')
    def validate_compliance_score(cls, v):
        if not 0.0 <= v <= 1.0:
            raise ValueError("compliance_score must be between 0.0 and 1.0")
        return v


class ComplianceFinding(BaseModel):
    """준수 발견사항"""
    finding_id: str = Field(description="발견사항 ID")
    title: str = Field(description="발견사항 제목")
    description: str = Field(description="발견사항 설명")
    severity: str = Field(description="심각도 (critical/high/medium/low)")
    
    # 규제 준수 정보
    compliance_standard: ComplianceStandard = Field(description="관련 준수 표준")
    control_id: str = Field(description="통제 ID")
    control_description: str = Field(description="통제 설명")
    
    # 위반 정보
    violation_type: str = Field(description="위반 유형")
    violation_count: int = Field(description="위반 횟수")
    first_occurrence: datetime = Field(description="첫 발생 시각")
    last_occurrence: datetime = Field(description="마지막 발생 시각")
    
    # 영향도
    impact_description: str = Field(description="영향도 설명")
    business_impact: str = Field(description="비즈니스 영향")
    affected_systems: List[str] = Field(default_factory=list, description="영향받은 시스템")
    affected_users: List[str] = Field(default_factory=list, description="영향받은 사용자")
    
    # 증거
    evidence: List[Dict[str, Any]] = Field(default_factory=list, description="증거 자료")
    related_events: List[str] = Field(default_factory=list, description="관련 이벤트 ID")
    
    # 해결 정보
    remediation_status: str = Field(default="open", description="해결 상태 (open/in_progress/resolved)")
    assigned_to: Optional[str] = Field(None, description="담당자")
    due_date: Optional[datetime] = Field(None, description="해결 기한")


class ComplianceRecommendation(BaseModel):
    """준수 권고사항"""
    recommendation_id: str = Field(description="권고사항 ID")
    title: str = Field(description="권고사항 제목")
    description: str = Field(description="권고사항 설명")
    priority: str = Field(description="우선순위 (critical/high/medium/low)")
    
    # 구현 정보
    implementation_effort: str = Field(description="구현 노력 (low/medium/high)")
    estimated_cost: Optional[str] = Field(None, description="예상 비용")
    timeline: Optional[str] = Field(None, description="구현 일정")
    
    # 관련 정보
    related_findings: List[str] = Field(default_factory=list, description="관련 발견사항 ID")
    related_controls: List[str] = Field(default_factory=list, description="관련 통제 ID")
    
    # 구현 단계
    implementation_steps: List[str] = Field(default_factory=list, description="구현 단계")
    success_criteria: List[str] = Field(default_factory=list, description="성공 기준")


class AuditReport(BaseModel):
    """감사 리포트"""
    # 기본 정보
    report_id: str = Field(description="리포트 ID")
    report_type: ReportType = Field(description="리포트 타입")
    title: str = Field(description="리포트 제목")
    description: Optional[str] = Field(None, description="리포트 설명")
    
    # 생성 정보
    generated_by: str = Field(description="생성자 ID")
    generated_at: datetime = Field(description="생성 시각")
    period_start: datetime = Field(description="리포트 기간 시작")
    period_end: datetime = Field(description="리포트 기간 종료")
    
    # 상태 정보
    status: ReportStatus = Field(description="리포트 상태")
    generation_time_ms: Optional[int] = Field(None, description="생성 시간 (밀리초)")
    
    # 데이터 범위
    included_systems: List[str] = Field(default_factory=list, description="포함된 시스템")
    included_users: List[str] = Field(default_factory=list, description="포함된 사용자")
    event_types: List[str] = Field(default_factory=list, description="포함된 이벤트 타입")
    
    # 요약 통계
    summary: Dict[str, Any] = Field(default_factory=dict, description="요약 통계")
    key_metrics: Dict[str, Any] = Field(default_factory=dict, description="주요 지표")
    
    # 섹션별 내용
    sections: List['ReportSection'] = Field(default_factory=list, description="리포트 섹션")
    
    # 파일 정보
    file_path: Optional[str] = Field(None, description="생성된 파일 경로")
    file_size_bytes: Optional[int] = Field(None, description="파일 크기")
    download_url: Optional[str] = Field(None, description="다운로드 URL")
    expires_at: Optional[datetime] = Field(None, description="만료 시각")
    
    # 배포 정보
    recipients: List[str] = Field(default_factory=list, description="수신자 목록")
    distribution_status: Dict[str, str] = Field(default_factory=dict, description="배포 상태")
    
    # 메타데이터
    metadata: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")


class ReportSection(BaseModel):
    """리포트 섹션"""
    section_id: str = Field(description="섹션 ID")
    title: str = Field(description="섹션 제목")
    order: int = Field(description="섹션 순서")
    
    # 내용
    content_type: str = Field(description="내용 타입 (text/table/chart/graph)")
    content: Dict[str, Any] = Field(description="섹션 내용")
    
    # 시각화
    charts: List[Dict[str, Any]] = Field(default_factory=list, description="차트 데이터")
    tables: List[Dict[str, Any]] = Field(default_factory=list, description="테이블 데이터")
    
    # 메타데이터
    metadata: Dict[str, Any] = Field(default_factory=dict, description="섹션 메타데이터")


class ReportTemplate(BaseModel):
    """리포트 템플릿"""
    template_id: str = Field(description="템플릿 ID")
    name: str = Field(description="템플릿 이름")
    description: Optional[str] = Field(None, description="템플릿 설명")
    report_type: ReportType = Field(description="리포트 타입")
    compliance_standard: Optional[ComplianceStandard] = Field(None, description="준수 표준")
    
    # 템플릿 정의
    sections: List[Dict[str, Any]] = Field(description="섹션 정의")
    default_parameters: Dict[str, Any] = Field(default_factory=dict, description="기본 매개변수")
    
    # 생성 정보
    created_by: str = Field(description="생성자 ID")
    created_at: datetime = Field(description="생성 시각")
    updated_by: Optional[str] = Field(None, description="수정자 ID")
    updated_at: Optional[datetime] = Field(None, description="수정 시각")
    
    # 상태
    is_active: bool = Field(default=True, description="활성 상태")
    version: str = Field(description="템플릿 버전")


class ReportSchedule(BaseModel):
    """리포트 스케줄"""
    schedule_id: str = Field(description="스케줄 ID")
    name: str = Field(description="스케줄 이름")
    description: Optional[str] = Field(None, description="스케줄 설명")
    
    # 리포트 설정
    template_id: str = Field(description="사용할 템플릿 ID")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="리포트 매개변수")
    
    # 스케줄링
    cron_expression: str = Field(description="크론 표현식")
    timezone: str = Field(default="UTC", description="시간대")
    enabled: bool = Field(default=True, description="활성화 여부")
    
    # 배포 설정
    recipients: List[str] = Field(description="수신자 목록")
    delivery_method: str = Field(description="배달 방식 (email/webhook/s3)")
    delivery_config: Dict[str, Any] = Field(default_factory=dict, description="배달 설정")
    
    # 생성 정보
    created_by: str = Field(description="생성자 ID")
    created_at: datetime = Field(description="생성 시각")
    
    # 실행 정보
    last_run_at: Optional[datetime] = Field(None, description="마지막 실행 시각")
    next_run_at: Optional[datetime] = Field(None, description="다음 실행 시각")
    run_count: int = Field(default=0, description="실행 횟수")
    
    @field_validator('cron_expression')
    def validate_cron_expression(cls, v):
        # 기본적인 크론 표현식 검증 (5개 필드)
        parts = v.split()
        if len(parts) != 5:
            raise ValueError("cron_expression must have 5 fields")
        return v