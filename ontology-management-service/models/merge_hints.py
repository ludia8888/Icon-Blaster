"""
병합 힌트 메타데이터 정의

스키마에 병합 전략을 명시하기 위한 메타데이터 모델
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class MergeStrategy(str, Enum):
    """병합 전략 타입"""
    LCS_REORDERABLE = "lcs-reorderable"  # 순서가 중요한 리스트
    UNORDERED_SET = "unordered-set"      # 순서가 중요하지 않은 집합
    KEYED_MAP = "keyed-map"              # 키로 식별되는 맵
    ATOMIC = "atomic"                     # 원자적 단위로 처리
    CUSTOM = "custom"                     # 커스텀 병합 로직


class ConflictResolution(str, Enum):
    """충돌 해결 전략"""
    MANUAL = "manual"                     # 수동 해결 필요
    PREFER_SOURCE = "prefer-source"       # 소스 우선
    PREFER_TARGET = "prefer-target"       # 타겟 우선
    MERGE_BOTH = "merge-both"            # 양쪽 병합 시도
    FAIL_FAST = "fail-fast"              # 즉시 실패


class MergeHint(BaseModel):
    """병합 힌트 메타데이터"""
    
    strategy: MergeStrategy = Field(
        default=MergeStrategy.KEYED_MAP,
        description="병합 전략"
    )
    
    identity_key: Optional[str] = Field(
        default=None,
        description="리스트/맵 항목을 식별하는 키 (예: 'name', 'id')"
    )
    
    order_field: Optional[str] = Field(
        default=None,
        description="순서를 나타내는 필드 이름 (예: 'order', 'sortOrder')"
    )
    
    conflict_resolution: ConflictResolution = Field(
        default=ConflictResolution.MANUAL,
        description="충돌 해결 전략"
    )
    
    preserve_order: bool = Field(
        default=False,
        description="순서 정보 보존 여부"
    )
    
    semantic_groups: Optional[List[List[str]]] = Field(
        default=None,
        description="함께 처리되어야 하는 필드 그룹들"
    )
    
    validation_rules: Optional[List[str]] = Field(
        default=None,
        description="병합 후 검증 규칙 (표현식)"
    )
    
    custom_merger: Optional[str] = Field(
        default=None,
        description="커스텀 병합 함수 이름"
    )


class PropertyMergeHint(MergeHint):
    """Property 배열 병합을 위한 힌트"""
    
    # Property 특화 설정
    merge_property_groups: bool = Field(
        default=True,
        description="관련 속성들을 그룹으로 병합"
    )
    
    handle_type_changes: bool = Field(
        default=True,
        description="타입 변경 자동 처리"
    )


class FieldMergeHint(BaseModel):
    """개별 필드에 대한 병합 힌트"""
    
    field_name: str = Field(..., description="필드 이름")
    
    merge_hint: MergeHint = Field(
        ...,
        description="해당 필드의 병합 힌트"
    )


class SchemaMergeMetadata(BaseModel):
    """
    스키마 전체의 병합 메타데이터
    
    ObjectType이나 다른 스키마 정의에 추가되는 메타데이터
    """
    
    # 기본 병합 전략
    default_strategy: MergeStrategy = Field(
        default=MergeStrategy.KEYED_MAP,
        description="기본 병합 전략"
    )
    
    # 필드별 병합 힌트
    field_hints: Dict[str, MergeHint] = Field(
        default_factory=dict,
        description="필드별 병합 힌트"
    )
    
    # 특별 처리가 필요한 필드들
    properties_hint: Optional[PropertyMergeHint] = Field(
        default=None,
        description="properties 배열 병합 힌트"
    )
    
    # 의미론적 필드 그룹
    semantic_field_groups: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="의미론적으로 연관된 필드 그룹 정의"
    )
    
    # 상태 전이 규칙 (기존 모델과 연동)
    enforce_state_transitions: bool = Field(
        default=True,
        description="상태 전이 규칙 적용 여부"
    )
    
    # 병합 검증 규칙
    post_merge_validations: Optional[List[str]] = Field(
        default=None,
        description="병합 후 실행할 검증 규칙들"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "default_strategy": "keyed-map",
                "field_hints": {
                    "properties": {
                        "strategy": "lcs-reorderable",
                        "identity_key": "name",
                        "preserve_order": True,
                        "conflict_resolution": "manual"
                    },
                    "interfaces": {
                        "strategy": "unordered-set",
                        "identity_key": "name"
                    }
                },
                "properties_hint": {
                    "merge_property_groups": True,
                    "handle_type_changes": True
                },
                "semantic_field_groups": [
                    {
                        "name": "tax_info",
                        "fields": ["isTaxable", "taxRate", "taxExemptionReason"],
                        "merge_as_unit": True
                    }
                ]
            }
        }


def get_merge_hint_for_field(
    schema_metadata: Optional[SchemaMergeMetadata],
    field_name: str
) -> Optional[MergeHint]:
    """특정 필드의 병합 힌트 조회"""
    if not schema_metadata:
        return None
    
    # 필드별 힌트 확인
    if field_name in schema_metadata.field_hints:
        return schema_metadata.field_hints[field_name]
    
    # properties 필드 특별 처리
    if field_name == "properties" and schema_metadata.properties_hint:
        return schema_metadata.properties_hint
    
    return None


def create_default_merge_hints() -> SchemaMergeMetadata:
    """기본 병합 힌트 생성"""
    return SchemaMergeMetadata(
        default_strategy=MergeStrategy.KEYED_MAP,
        field_hints={
            "properties": MergeHint(
                strategy=MergeStrategy.LCS_REORDERABLE,
                identity_key="name",
                preserve_order=True,
                conflict_resolution=ConflictResolution.MANUAL
            ),
            "parentTypes": MergeHint(
                strategy=MergeStrategy.UNORDERED_SET,
                conflict_resolution=ConflictResolution.MERGE_BOTH
            ),
            "interfaces": MergeHint(
                strategy=MergeStrategy.UNORDERED_SET,
                conflict_resolution=ConflictResolution.MERGE_BOTH
            ),
            "fieldGroups": MergeHint(
                strategy=MergeStrategy.KEYED_MAP,
                identity_key="name",
                conflict_resolution=ConflictResolution.MANUAL
            )
        },
        enforce_state_transitions=True
    )