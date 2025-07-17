"""
TerminusDB to Foundry Conflict Format Converter
JSON-LD 경로 매핑 및 충돌 형식 변환
"""

import json
import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class ConflictSeverity(Enum):
    """충돌 심각도"""
    LOW = "low"
    MEDIUM = "medium" 
    HIGH = "high"
    CRITICAL = "critical"


class PathType(Enum):
    """JSON-LD 경로 타입"""
    CLASS_PROPERTY = "class_property"
    RELATIONSHIP = "relationship"
    DATA_TYPE = "data_type"
    ANNOTATION = "annotation"
    SCHEMA_REFERENCE = "schema_reference"
    UNKNOWN = "unknown"


@dataclass
class JsonLdPath:
    """JSON-LD 경로 분석 결과"""
    full_path: str
    namespace: Optional[str]
    property_name: str
    path_type: PathType
    human_readable: str
    context: Dict[str, Any]


@dataclass
class ConflictAnalysis:
    """충돌 분석 결과"""
    conflict_type: str
    severity: ConflictSeverity
    auto_resolvable: bool
    suggested_resolution: str
    impact_analysis: Dict[str, Any]


class ConflictConverter:
    """TerminusDB 충돌을 Foundry 스타일로 변환하는 클래스"""
    
    def __init__(self):
        # JSON-LD 네임스페이스 매핑
        self.namespace_mappings = {
            "http://www.w3.org/1999/02/22-rdf-syntax-ns#": "rdf:",
            "http://www.w3.org/2000/01/rdf-schema#": "rdfs:",
            "http://www.w3.org/2002/07/owl#": "owl:",
            "http://schema.org/": "schema:",
            "http://example.org/ontology#": "onto:",
            "@type": "type",
            "@id": "id",
            "@context": "context"
        }
        
        # 한국어 속성명 매핑
        self.korean_property_mappings = {
            "rdfs:label": "이름",
            "rdfs:comment": "설명", 
            "owl:Class": "클래스",
            "owl:ObjectProperty": "객체 속성",
            "owl:DatatypeProperty": "데이터 속성",
            "rdf:type": "타입",
            "owl:subClassOf": "상위 클래스",
            "owl:equivalentClass": "동등 클래스",
            "owl:disjointWith": "서로소 클래스"
        }
    
    async def convert_conflicts_to_foundry_format(
        self, 
        terminus_conflicts: List[Dict[str, Any]], 
        db_name: str,
        source_branch: str,
        target_branch: str
    ) -> List[Dict[str, Any]]:
        """
        TerminusDB 충돌을 Foundry 스타일로 변환
        
        Args:
            terminus_conflicts: TerminusDB 형식의 충돌 목록
            db_name: 데이터베이스 이름
            source_branch: 소스 브랜치
            target_branch: 대상 브랜치
            
        Returns:
            Foundry 스타일 충돌 목록
        """
        foundry_conflicts = []
        
        for i, conflict in enumerate(terminus_conflicts):
            try:
                foundry_conflict = await self._convert_single_conflict(
                    conflict, i + 1, db_name, source_branch, target_branch
                )
                foundry_conflicts.append(foundry_conflict)
                
            except Exception as e:
                logger.warning(f"Failed to convert conflict {i}: {e}")
                # 변환 실패 시 기본 충돌 정보 생성
                fallback_conflict = self._create_fallback_conflict(conflict, i + 1)
                foundry_conflicts.append(fallback_conflict)
        
        return foundry_conflicts
    
    async def _convert_single_conflict(
        self, 
        conflict: Dict[str, Any], 
        conflict_id: int,
        db_name: str,
        source_branch: str,
        target_branch: str
    ) -> Dict[str, Any]:
        """단일 충돌을 Foundry 형식으로 변환"""
        
        # 1. JSON-LD 경로 분석
        path_info = await self._analyze_jsonld_path(conflict.get("path", "unknown"))
        
        # 2. 충돌 분석 수행
        conflict_analysis = await self._analyze_conflict(conflict, path_info)
        
        # 3. 충돌 데이터 추출
        source_change = conflict.get("source_change", {})
        target_change = conflict.get("target_change", {})
        
        # 4. 값 비교 및 유형 분석
        source_value, source_type = self._extract_value_and_type(source_change)
        target_value, target_type = self._extract_value_and_type(target_change)
        
        # 5. Foundry 충돌 객체 생성
        foundry_conflict = {
            "id": f"conflict_{conflict_id}",
            "type": conflict_analysis.conflict_type,
            "severity": conflict_analysis.severity.value,
            "path": {
                "raw": path_info.full_path,
                "human_readable": path_info.human_readable,
                "namespace": path_info.namespace,
                "property": path_info.property_name,
                "type": path_info.path_type.value
            },
            "description": self._generate_conflict_description(
                path_info, source_change, target_change
            ),
            "sides": {
                "source": {
                    "branch": source_branch,
                    "value": source_value,
                    "value_type": source_type,
                    "change_type": source_change.get("type", "unknown"),
                    "label": "소스 브랜치 변경사항",
                    "preview": self._generate_value_preview(source_value, source_type)
                },
                "target": {
                    "branch": target_branch,
                    "value": target_value,
                    "value_type": target_type,
                    "change_type": target_change.get("type", "unknown"),
                    "label": "대상 브랜치 변경사항",
                    "preview": self._generate_value_preview(target_value, target_type)
                }
            },
            "resolution": {
                "auto_resolvable": conflict_analysis.auto_resolvable,
                "suggested_strategy": conflict_analysis.suggested_resolution,
                "options": self._generate_resolution_options(
                    source_value, target_value, conflict_analysis
                )
            },
            "impact": conflict_analysis.impact_analysis,
            "metadata": {
                "database": db_name,
                "conflict_source": "terminus_db",
                "created_at": self._get_current_timestamp(),
                "path_context": path_info.context
            }
        }
        
        return foundry_conflict
    
    async def _analyze_jsonld_path(self, path: str) -> JsonLdPath:
        """JSON-LD 경로 분석"""
        
        # 네임스페이스 분리
        namespace, property_name = self._split_namespace_and_property(path)
        
        # 경로 타입 결정
        path_type = self._determine_path_type(path, property_name)
        
        # 사람이 읽기 쉬운 형태로 변환
        human_readable = self._convert_to_human_readable(namespace, property_name)
        
        # 컨텍스트 정보 수집
        context = {
            "original_path": path,
            "namespace_mapping": self.namespace_mappings.get(namespace, namespace),
            "korean_name": self.korean_property_mappings.get(f"{namespace}{property_name}", property_name)
        }
        
        return JsonLdPath(
            full_path=path,
            namespace=namespace,
            property_name=property_name,
            path_type=path_type,
            human_readable=human_readable,
            context=context
        )
    
    def _split_namespace_and_property(self, path: str) -> Tuple[Optional[str], str]:
        """네임스페이스와 속성명 분리"""
        
        # URI 형태인 경우
        if path.startswith("http"):
            # 마지막 # 또는 / 뒤의 내용을 속성명으로 처리
            if "#" in path:
                namespace = path.rsplit("#", 1)[0] + "#"
                property_name = path.rsplit("#", 1)[1]
            elif "/" in path:
                namespace = path.rsplit("/", 1)[0] + "/"
                property_name = path.rsplit("/", 1)[1]
            else:
                namespace = None
                property_name = path
        # 축약형인 경우 (예: rdfs:label)
        elif ":" in path:
            parts = path.split(":", 1)
            namespace = parts[0] + ":"
            property_name = parts[1]
        else:
            namespace = None
            property_name = path
            
        return namespace, property_name
    
    def _determine_path_type(self, full_path: str, property_name: str) -> PathType:
        """경로 타입 결정"""
        
        # RDF/OWL 표준 속성들
        if property_name in ["type", "Class", "ObjectProperty", "DatatypeProperty"]:
            return PathType.CLASS_PROPERTY
        elif property_name in ["subClassOf", "equivalentClass", "disjointWith"]:
            return PathType.RELATIONSHIP
        elif property_name in ["label", "comment"]:
            return PathType.ANNOTATION
        elif property_name.startswith("xsd:") or "datatype" in property_name.lower():
            return PathType.DATA_TYPE
        elif full_path.startswith("http://schema.org/"):
            return PathType.SCHEMA_REFERENCE
        else:
            return PathType.UNKNOWN
    
    def _convert_to_human_readable(self, namespace: Optional[str], property_name: str) -> str:
        """사람이 읽기 쉬운 형태로 변환"""
        
        # 한국어 매핑이 있는 경우
        full_key = f"{namespace or ''}{property_name}"
        if full_key in self.korean_property_mappings:
            return self.korean_property_mappings[full_key]
        
        # 네임스페이스 축약
        if namespace and namespace in self.namespace_mappings:
            prefix = self.namespace_mappings[namespace]
            return f"{prefix}{property_name}"
        
        # camelCase를 공백으로 분리
        readable = re.sub(r'([a-z])([A-Z])', r'\1 \2', property_name)
        
        return readable
    
    async def _analyze_conflict(
        self, 
        conflict: Dict[str, Any], 
        path_info: JsonLdPath
    ) -> ConflictAnalysis:
        """충돌 분석 수행"""
        
        source_change = conflict.get("source_change", {})
        target_change = conflict.get("target_change", {})
        
        # 충돌 타입 결정
        conflict_type = self._determine_conflict_type(source_change, target_change, path_info)
        
        # 심각도 평가
        severity = self._assess_severity(conflict_type, path_info, source_change, target_change)
        
        # 자동 해결 가능성 평가
        auto_resolvable = self._assess_auto_resolvability(
            conflict_type, source_change, target_change
        )
        
        # 해결 방법 제안
        suggested_resolution = self._suggest_resolution_strategy(
            conflict_type, source_change, target_change, auto_resolvable
        )
        
        # 영향 분석
        impact_analysis = self._analyze_impact(conflict_type, path_info, source_change, target_change)
        
        return ConflictAnalysis(
            conflict_type=conflict_type,
            severity=severity,
            auto_resolvable=auto_resolvable,
            suggested_resolution=suggested_resolution,
            impact_analysis=impact_analysis
        )
    
    def _determine_conflict_type(
        self, 
        source_change: Dict[str, Any], 
        target_change: Dict[str, Any],
        path_info: JsonLdPath
    ) -> str:
        """충돌 타입 결정"""
        
        source_type = source_change.get("type", "unknown")
        target_type = target_change.get("type", "unknown")
        
        if source_type == "add" and target_type == "add":
            return "add_add_conflict"
        elif source_type == "modify" and target_type == "modify":
            return "modify_modify_conflict"
        elif source_type == "delete" and target_type == "modify":
            return "delete_modify_conflict"
        elif source_type == "modify" and target_type == "delete":
            return "modify_delete_conflict"
        elif source_type == "delete" and target_type == "delete":
            return "delete_delete_conflict"
        else:
            return "unknown_conflict"
    
    def _assess_severity(
        self, 
        conflict_type: str, 
        path_info: JsonLdPath,
        source_change: Dict[str, Any], 
        target_change: Dict[str, Any]
    ) -> ConflictSeverity:
        """충돌 심각도 평가"""
        
        # 스키마 관련 충돌은 높은 심각도
        if path_info.path_type in [PathType.CLASS_PROPERTY, PathType.RELATIONSHIP]:
            return ConflictSeverity.HIGH
        
        # 삭제 관련 충돌은 심각도가 높음
        if "delete" in conflict_type:
            return ConflictSeverity.HIGH
        
        # 어노테이션 충돌은 낮은 심각도
        if path_info.path_type == PathType.ANNOTATION:
            return ConflictSeverity.LOW
        
        # 기본값
        return ConflictSeverity.MEDIUM
    
    def _assess_auto_resolvability(
        self, 
        conflict_type: str, 
        source_change: Dict[str, Any], 
        target_change: Dict[str, Any]
    ) -> bool:
        """자동 해결 가능성 평가"""
        
        # 동일한 값으로의 변경은 자동 해결 가능
        source_val = source_change.get("new_value")
        target_val = target_change.get("new_value")
        
        if source_val == target_val:
            return True
        
        # 단순 텍스트 추가는 병합 가능할 수 있음
        if conflict_type == "add_add_conflict":
            return False  # 보수적으로 수동 해결 요구
        
        return False
    
    def _suggest_resolution_strategy(
        self, 
        conflict_type: str, 
        source_change: Dict[str, Any], 
        target_change: Dict[str, Any],
        auto_resolvable: bool
    ) -> str:
        """해결 방법 제안"""
        
        if auto_resolvable:
            return "automatic"
        
        if "delete" in conflict_type:
            return "manual_review_required"
        elif conflict_type == "modify_modify_conflict":
            return "choose_side_or_merge"
        elif conflict_type == "add_add_conflict":
            return "manual_merge_required"
        else:
            return "manual"
    
    def _analyze_impact(
        self, 
        conflict_type: str, 
        path_info: JsonLdPath,
        source_change: Dict[str, Any], 
        target_change: Dict[str, Any]
    ) -> Dict[str, Any]:
        """영향 분석"""
        
        return {
            "schema_breaking": path_info.path_type == PathType.CLASS_PROPERTY,
            "data_loss_risk": "delete" in conflict_type,
            "backward_compatibility": conflict_type not in ["delete_modify_conflict", "modify_delete_conflict"],
            "affected_properties": [path_info.property_name],
            "estimated_complexity": "low" if path_info.path_type == PathType.ANNOTATION else "medium"
        }
    
    def _extract_value_and_type(self, change: Dict[str, Any]) -> Tuple[Any, str]:
        """변경사항에서 값과 타입 추출"""
        
        value = change.get("new_value", change.get("value"))
        
        if isinstance(value, dict):
            return value, "object"
        elif isinstance(value, list):
            return value, "array"
        elif isinstance(value, str):
            return value, "string"
        elif isinstance(value, (int, float)):
            return value, "number"
        elif isinstance(value, bool):
            return value, "boolean"
        else:
            return str(value), "unknown"
    
    def _generate_value_preview(self, value: Any, value_type: str) -> str:
        """값 미리보기 생성"""
        
        if value_type == "string":
            return value[:100] + ("..." if len(str(value)) > 100 else "")
        elif value_type == "object":
            return json.dumps(value, ensure_ascii=False)[:100] + "..."
        elif value_type == "array":
            return f"배열 (항목 {len(value)}개)"
        else:
            return str(value)
    
    def _generate_conflict_description(
        self, 
        path_info: JsonLdPath, 
        source_change: Dict[str, Any], 
        target_change: Dict[str, Any]
    ) -> str:
        """충돌 설명 생성"""
        
        human_readable = path_info.human_readable
        source_type = source_change.get("type", "변경")
        target_type = target_change.get("type", "변경")
        
        return f"'{human_readable}' 속성에서 소스 브랜치는 {source_type}, 대상 브랜치는 {target_type}을 수행했습니다."
    
    def _generate_resolution_options(
        self, 
        source_value: Any, 
        target_value: Any, 
        analysis: ConflictAnalysis
    ) -> List[Dict[str, Any]]:
        """해결 옵션 생성"""
        
        options = [
            {
                "id": "use_source",
                "label": "소스 브랜치 값 사용",
                "description": "소스 브랜치의 변경사항을 적용합니다",
                "value": source_value,
                "recommended": False
            },
            {
                "id": "use_target", 
                "label": "대상 브랜치 값 사용",
                "description": "대상 브랜치의 기존 값을 유지합니다",
                "value": target_value,
                "recommended": False
            }
        ]
        
        # 수동 병합 옵션 추가 (필요한 경우)
        if analysis.suggested_resolution == "manual_merge_required":
            options.append({
                "id": "manual_merge",
                "label": "수동 병합",
                "description": "사용자가 직접 값을 입력합니다",
                "value": None,
                "recommended": True
            })
        
        return options
    
    def _create_fallback_conflict(self, conflict: Dict[str, Any], conflict_id: int) -> Dict[str, Any]:
        """변환 실패 시 기본 충돌 정보 생성"""
        
        return {
            "id": f"conflict_{conflict_id}",
            "type": "unknown_conflict",
            "severity": "medium",
            "path": {
                "raw": conflict.get("path", "unknown"),
                "human_readable": "알 수 없는 속성",
                "namespace": None,
                "property": "unknown",
                "type": "unknown"
            },
            "description": "충돌 정보를 분석할 수 없습니다.",
            "sides": {
                "source": {
                    "value": conflict.get("source_change", {}).get("new_value"),
                    "label": "소스 브랜치 변경사항"
                },
                "target": {
                    "value": conflict.get("target_change", {}).get("new_value"),
                    "label": "대상 브랜치 변경사항"
                }
            },
            "resolution": {
                "auto_resolvable": False,
                "suggested_strategy": "manual",
                "options": []
            },
            "metadata": {
                "conversion_error": True,
                "original_conflict": conflict
            }
        }
    
    def _get_current_timestamp(self) -> str:
        """현재 타임스탬프 반환"""
        from datetime import datetime
        return datetime.utcnow().isoformat()