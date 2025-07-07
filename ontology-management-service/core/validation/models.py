"""
Validation Service 도메인 모델
섹션 8.3의 Validation Service 명세 구현
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class Severity(str, Enum):
    """Breaking change 심각도"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MigrationStrategy(str, Enum):
    """마이그레이션 전략"""
    COPY_THEN_DROP = "copy-then-drop"
    BACKFILL_NULLABLE = "backfill-nullable"
    SET_DEFAULT_VALUES = "set-default-values"
    MAKE_NULLABLE_FIRST = "make-nullable-first"
    ATOMIC_SWITCH = "atomic-switch"
    PROGRESSIVE_ROLLOUT = "progressive-rollout"


class ImpactEstimate(BaseModel):
    """영향도 추정"""
    affected_records: int
    estimated_duration_seconds: float
    requires_downtime: bool
    affected_services: List[str] = Field(default_factory=list)
    affected_apis: List[str] = Field(default_factory=list)


class DataImpact(BaseModel):
    """데이터 영향도 분석 (UC-02 요구사항)"""
    total_records: int
    affected_records: int
    impact_percentage: float
    estimated_downtime_minutes: int
    complexity_score: int  # 1-10 scale
    migration_risks: List[str] = Field(default_factory=list)


class BreakingChange(BaseModel):
    """Breaking Change 정보 (Foundry OMS Enhanced)"""
    rule_id: str
    severity: Severity
    resource_type: str  # ObjectType, Property, LinkType 등
    resource_id: str
    resource_name: Optional[str] = None
    change_type: Optional[str] = None  # Foundry 특화 변경 유형
    description: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None

    # Enhanced impact analysis (UC-02)
    data_impact: Optional[DataImpact] = None
    impact_estimate: Optional[ImpactEstimate] = None  # Legacy compatibility

    # Foundry-specific fields
    migration_strategy: Optional[str] = None  # Generated strategy text
    foundry_compliance: Optional[str] = None  # Foundry compatibility assessment

    # Legacy fields
    migration_strategies: List[MigrationStrategy] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidationWarning(BaseModel):
    """검증 경고"""
    rule_id: str
    resource_type: str
    resource_id: str
    description: str
    recommendation: Optional[str] = None


class ValidationResult(BaseModel):
    """검증 결과"""
    validation_id: str
    source_branch: str
    target_branch: str
    is_valid: bool
    breaking_changes: List[BreakingChange] = Field(default_factory=list)
    warnings: List[ValidationWarning] = Field(default_factory=list)
    impact_analysis: Optional[Dict[str, Any]] = None
    suggested_migrations: List[str] = Field(default_factory=list)
    performance_metrics: Optional[Dict[str, Any]] = None
    validated_at: datetime = Field(default_factory=datetime.utcnow)
    rule_execution_results: Dict[str, Any] = Field(default_factory=dict)


class ValidationRequest(BaseModel):
    """검증 요청"""
    source_branch: str
    target_branch: str = "main"
    include_warnings: bool = True
    include_impact_analysis: bool = True
    custom_rules: List[str] = Field(default_factory=list)
    options: Dict[str, Any] = Field(default_factory=dict)


class MigrationStep(BaseModel):
    """마이그레이션 단계"""
    type: str  # create_temp_collection, copy_with_transformation 등
    description: str
    woql_script: Optional[str] = None
    estimated_duration: float
    can_parallel: bool = False
    requires_downtime: bool = False
    downtime_duration: Optional[float] = None
    batch_size: Optional[int] = None
    rollback_script: Optional[str] = None
    verification_script: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MigrationPlan(BaseModel):
    """마이그레이션 계획"""
    id: str
    breaking_changes: List[BreakingChange]
    target_branch: str
    steps: List[MigrationStep]
    rollback_steps: List[MigrationStep]
    execution_order: List[str]  # ObjectType 이름들의 순서
    estimated_duration: float
    requires_downtime: bool
    downtime_windows: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    created_by: Optional[str] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    status: str = "draft"  # draft, approved, executing, completed, failed


class MigrationOptions(BaseModel):
    """마이그레이션 옵션"""
    strategy: MigrationStrategy = MigrationStrategy.COPY_THEN_DROP
    batch_size: int = 1000
    parallel_workers: int = 4
    dry_run: bool = False
    rollback_on_error: bool = True
    verification_enabled: bool = True
    notification_webhook: Optional[str] = None


class ValidationContext(BaseModel):
    """검증 컨텍스트 (Foundry OMS Enhanced)"""
    source_branch: str
    target_branch: str
    source_schema: Dict[str, Any]
    target_schema: Dict[str, Any]
    common_ancestor: Optional[Dict[str, Any]] = None

    # Foundry-specific context
    terminus_client: Optional[Any] = None  # TerminusDBClient instance
    cache: Optional[Any] = None  # Cache manager instance
    event_publisher: Optional[Any] = None  # Event publisher instance

    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True  # Allow non-Pydantic types


class RuleExecutionResult(BaseModel):
    """규칙 실행 결과"""
    rule_id: str
    executed: bool
    execution_time_ms: float
    breaking_changes_found: int
    warnings_found: int
    error: Optional[str] = None


class CustomValidationRule(BaseModel):
    """커스텀 검증 규칙"""
    id: str
    name: str
    description: str
    severity: Severity
    rule_expression: str  # WOQL 표현식
    applies_to: List[str]  # 적용 대상 리소스 타입
    enabled: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)
