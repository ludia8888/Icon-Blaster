"""
REQ-OMS-F2-AC3: 3-Way Merge 알고리즘
REQ-OMS-F2-AC4: Preview 기능 지원
섹션 11.1.1의 Git 스타일 3-way merge 알고리즘 구현
"""
import logging
from typing import Any, Dict, List, Optional

from services.branch_service.core.models import (
    Conflict,
    FieldConflict,
    FieldMergeResult,
    MergeResult,
    MergeStatistics,
    ResourceMergeResult,
)
from shared.clients.terminus_db import TerminusDBClient

logger = logging.getLogger(__name__)


class ConflictDetector:
    """
    REQ-OMS-F2-AC3: 충돌 감지기
    3-way diff 기반 충돌 감지 알고리즘
    """
    pass


class ThreeWayMergeAlgorithm:
    """
    REQ-OMS-F2-AC3: Git 스타일 3-way merge 알고리즘 구현
    충돌 감지 및 자동 머지 지원
    """

    def __init__(self, tdb_client: TerminusDBClient):
        self.tdb = tdb_client
        self.conflict_detector = ConflictDetector()

    async def merge(
        self,
        base_version: str,
        source_version: str,
        target_version: str
    ) -> MergeResult:
        """
        REQ-OMS-F2-AC3: 3-way merge 실행
        REQ-OMS-F2-AC4: 머지 결과 Preview 지원
        """

        # 1. 각 버전의 스키마 스냅샷 로드
        base_schemas = await self._load_schemas(base_version)
        source_schemas = await self._load_schemas(source_version)
        target_schemas = await self._load_schemas(target_version)

        # 2. 모든 리소스 ID 수집
        all_resources = set()
        all_resources.update(base_schemas.keys())
        all_resources.update(source_schemas.keys())
        all_resources.update(target_schemas.keys())

        # 3. 각 리소스에 대해 merge 수행
        merged_schemas = {}
        conflicts = []

        for resource_id in all_resources:
            base = base_schemas.get(resource_id)
            source = source_schemas.get(resource_id)
            target = target_schemas.get(resource_id)

            merge_result = self._merge_resource(
                resource_id, base, source, target
            )

            if merge_result.has_conflict:
                conflicts.append(merge_result.conflict)
            else:
                merged_schemas[resource_id] = merge_result.merged_value

        # 4. 결과 반환
        return MergeResult(
            merged_schemas=merged_schemas,
            conflicts=conflicts,
            statistics=self._calculate_statistics(
                base_schemas, source_schemas, target_schemas, merged_schemas
            )
        )

    def _merge_resource(
        self,
        resource_id: str,
        base: Optional[Dict],
        source: Optional[Dict],
        target: Optional[Dict]
    ) -> ResourceMergeResult:
        """단일 리소스 merge"""

        # 새로 추가된 리소스 처리
        if base is None:
            return self._handle_new_resource(resource_id, source, target)

        # 삭제된 리소스 처리
        if source is None or target is None:
            return self._handle_deleted_resource(
                resource_id, base, source, target
            )

        # 수정된 리소스 처리
        return self._handle_modified_resource(
            resource_id, base, source, target
        )

    def _handle_new_resource(
        self, resource_id: str, source: Optional[Dict], target: Optional[Dict]
    ) -> ResourceMergeResult:
        """새로 추가된 리소스 처리"""
        if source and target:
            # 양쪽에서 추가됨
            if self._schemas_equal(source, target):
                return ResourceMergeResult(
                    merged_value=source,
                    has_conflict=False
                )
            else:
                # ADD-ADD 충돌
                return self._create_conflict_result(
                    resource_id, "ADD_ADD", None, source, target
                )
        elif source:
            # Source에만 추가됨
            return ResourceMergeResult(
                merged_value=source,
                has_conflict=False
            )
        elif target:
            # Target에만 추가됨
            return ResourceMergeResult(
                merged_value=target,
                has_conflict=False
            )
        else:
            # 양쪽 모두 None - 발생하지 않아야 함
            return ResourceMergeResult(
                merged_value=None,
                has_conflict=False
            )

    def _handle_deleted_resource(
        self, resource_id: str, base: Dict,
        source: Optional[Dict], target: Optional[Dict]
    ) -> ResourceMergeResult:
        """삭제된 리소스 처리"""
        if source is None and target is None:
            # 양쪽에서 삭제됨
            return ResourceMergeResult(
                merged_value=None,
                has_conflict=False
            )
        elif source is None:
            # Source에서만 삭제됨
            return self._handle_delete_vs_modify(
                resource_id, base, target, "DELETE_MODIFY"
            )
        else:  # target is None
            # Target에서만 삭제됨
            return self._handle_modify_vs_delete(
                resource_id, base, source, "MODIFY_DELETE"
            )

    def _handle_delete_vs_modify(
        self, resource_id: str, base: Dict, modified: Dict, conflict_type: str
    ) -> ResourceMergeResult:
        """삭제 vs 수정 충돌 처리"""
        if self._schemas_equal(base, modified):
            # 수정 없음 - 삭제 적용
            return ResourceMergeResult(
                merged_value=None,
                has_conflict=False
            )
        else:
            # 수정됨 - 충돌
            source_val = None if conflict_type == "DELETE_MODIFY" else modified
            target_val = modified if conflict_type == "DELETE_MODIFY" else None
            return self._create_conflict_result(
                resource_id, conflict_type, base, source_val, target_val
            )

    def _handle_modify_vs_delete(
        self, resource_id: str, base: Dict, modified: Dict, conflict_type: str
    ) -> ResourceMergeResult:
        """수정 vs 삭제 충돌 처리"""
        if self._schemas_equal(base, modified):
            # 수정 없음 - 삭제 적용
            return ResourceMergeResult(
                merged_value=None,
                has_conflict=False
            )
        else:
            # 수정됨 - 충돌
            return self._create_conflict_result(
                resource_id, conflict_type, base, modified, None
            )

    def _handle_modified_resource(
        self, resource_id: str, base: Dict, source: Dict, target: Dict
    ) -> ResourceMergeResult:
        """수정된 리소스 처리"""
        source_changed = not self._schemas_equal(base, source)
        target_changed = not self._schemas_equal(base, target)

        # 변경 없음
        if not source_changed and not target_changed:
            return ResourceMergeResult(
                merged_value=base,
                has_conflict=False
            )

        # 한쪽만 변경됨
        if source_changed and not target_changed:
            return ResourceMergeResult(
                merged_value=source,
                has_conflict=False
            )
        if not source_changed and target_changed:
            return ResourceMergeResult(
                merged_value=target,
                has_conflict=False
            )

        # 양쪽 모두 변경됨
        return self._handle_both_modified(
            resource_id, base, source, target
        )

    def _handle_both_modified(
        self, resource_id: str, base: Dict, source: Dict, target: Dict
    ) -> ResourceMergeResult:
        """양쪽 모두 수정된 경우 처리"""
        if self._schemas_equal(source, target):
            # 동일하게 변경됨
            return ResourceMergeResult(
                merged_value=source,
                has_conflict=False
            )

        # 다르게 변경됨 - Field-level merge 시도
        field_merge_result = self._merge_fields(base, source, target)

        if field_merge_result.has_conflicts:
            return ResourceMergeResult(
                has_conflict=True,
                conflict=Conflict(
                    resource_id=resource_id,
                    conflict_type="MODIFY_MODIFY",
                    base_value=base,
                    source_value=source,
                    target_value=target,
                    field_conflicts=field_merge_result.conflicts
                )
            )
        else:
            return ResourceMergeResult(
                merged_value=field_merge_result.merged,
                has_conflict=False
            )

    def _create_conflict_result(
        self, resource_id: str, conflict_type: str,
        base_value: Optional[Dict], source_value: Optional[Dict],
        target_value: Optional[Dict]
    ) -> ResourceMergeResult:
        """충돌 결과 생성"""
        return ResourceMergeResult(
            has_conflict=True,
            conflict=Conflict(
                resource_id=resource_id,
                conflict_type=conflict_type,
                base_value=base_value,
                source_value=source_value,
                target_value=target_value
            )
        )

    def _merge_fields(
        self,
        base: Dict,
        source: Dict,
        target: Dict
    ) -> FieldMergeResult:
        """필드 레벨 merge"""

        merged = {}
        conflicts = []

        # 모든 필드 수집
        all_fields = set()
        all_fields.update(base.keys())
        all_fields.update(source.keys())
        all_fields.update(target.keys())

        # 시스템 필드는 제외
        all_fields = {f for f in all_fields if not f.startswith("@")}

        for field in all_fields:
            base_value = base.get(field)
            source_value = source.get(field)
            target_value = target.get(field)

            # 필드별 merge 로직
            if base_value == source_value == target_value:
                # 변경 없음
                merged[field] = base_value
            elif source_value == target_value:
                # 동일하게 변경됨
                merged[field] = source_value
            elif base_value == source_value:
                # Target만 변경됨
                merged[field] = target_value
            elif base_value == target_value:
                # Source만 변경됨
                merged[field] = source_value
            else:
                # 충돌 - 특별한 경우 처리
                if field == "properties" and isinstance(source_value, list):
                    # Properties 배열은 특별 처리
                    prop_merge = self._merge_properties(
                        base_value, source_value, target_value
                    )
                    if prop_merge.has_conflict:
                        conflicts.append(FieldConflict(
                            field=field,
                            base=base_value,
                            source=source_value,
                            target=target_value
                        ))
                    else:
                        merged[field] = prop_merge.merged
                else:
                    # 일반 필드 충돌
                    conflicts.append(FieldConflict(
                        field=field,
                        base=base_value,
                        source=source_value,
                        target=target_value
                    ))

        # 시스템 필드 복사
        for field in base:
            if field.startswith("@"):
                merged[field] = base[field]

        return FieldMergeResult(
            merged=merged,
            conflicts=conflicts,
            has_conflicts=len(conflicts) > 0
        )

    def _merge_properties(
        self,
        base_props: List[Dict],
        source_props: List[Dict],
        target_props: List[Dict]
    ) -> Dict[str, Any]:
        """Properties 배열 merge"""

        # Property를 이름으로 인덱싱
        base_by_name = {p.get("name"): p for p in (base_props or [])}
        source_by_name = {p.get("name"): p for p in (source_props or [])}
        target_by_name = {p.get("name"): p for p in (target_props or [])}

        # 모든 property 이름 수집
        all_prop_names = set()
        all_prop_names.update(base_by_name.keys())
        all_prop_names.update(source_by_name.keys())
        all_prop_names.update(target_by_name.keys())

        merged_props = []
        has_conflict = False

        for prop_name in all_prop_names:
            base_prop = base_by_name.get(prop_name)
            source_prop = source_by_name.get(prop_name)
            target_prop = target_by_name.get(prop_name)

            # 각 property에 대해 3-way merge 적용
            prop_merge_result = self._merge_resource(
                f"Property_{prop_name}",
                base_prop,
                source_prop,
                target_prop
            )

            if prop_merge_result.has_conflict:
                has_conflict = True
                # 충돌 발생 시 source 우선 (또는 다른 전략 사용)
                if source_prop:
                    merged_props.append(source_prop)
            elif prop_merge_result.merged_value:
                merged_props.append(prop_merge_result.merged_value)

        return {
            "merged": merged_props,
            "has_conflict": has_conflict
        }

    def _schemas_equal(self, schema1: Optional[Dict], schema2: Optional[Dict]) -> bool:
        """스키마 동등성 비교"""

        if schema1 is None and schema2 is None:
            return True
        if schema1 is None or schema2 is None:
            return False

        # 메타데이터 필드 제외하고 비교
        excluded_fields = {
            "createdAt", "createdBy", "modifiedAt", "modifiedBy",
            "versionHash", "@metadata"
        }

        schema1_filtered = {k: v for k, v in schema1.items() if k not in excluded_fields}
        schema2_filtered = {k: v for k, v in schema2.items() if k not in excluded_fields}

        return schema1_filtered == schema2_filtered

    async def _load_schemas(self, version: str) -> Dict[str, Dict]:
        """특정 버전의 스키마 스냅샷 로드"""

        query = """
        SELECT ?resource ?data
        WHERE {
            ?version ont:versionHash $version .
            ?version ont:snapshot ?snapshot .
            ?snapshot ont:resources ?resources .
            ?resources ont:resource ?resource .
            ?resource ont:data ?data .
        }
        """

        results = await self.tdb.query(
            query,
            branch="_versions",
            bindings={"version": version}
        )

        schemas = {}
        for result in results:
            resource_id = result.get("resource")
            data = result.get("data")
            if resource_id and data:
                schemas[resource_id] = data

        return schemas

    def _calculate_statistics(
        self,
        base_schemas: Dict[str, Dict],
        source_schemas: Dict[str, Dict],
        target_schemas: Dict[str, Dict],
        merged_schemas: Dict[str, Dict]
    ) -> MergeStatistics:
        """머지 통계 계산"""

        # 변경 사항 계산
        added_in_source = set(source_schemas.keys()) - set(base_schemas.keys())
        added_in_target = set(target_schemas.keys()) - set(base_schemas.keys())
        deleted_in_source = set(base_schemas.keys()) - set(source_schemas.keys())
        deleted_in_target = set(base_schemas.keys()) - set(target_schemas.keys())

        modified_in_source = {
            k for k in source_schemas
            if k in base_schemas and not self._schemas_equal(base_schemas[k], source_schemas[k])
        }

        modified_in_target = {
            k for k in target_schemas
            if k in base_schemas and not self._schemas_equal(base_schemas[k], target_schemas[k])
        }

        return MergeStatistics(
            total_resources=len(merged_schemas),
            added_count=len(added_in_source | added_in_target),
            modified_count=len(modified_in_source | modified_in_target),
            deleted_count=len(deleted_in_source | deleted_in_target),
            conflict_count=0,  # Will be set by caller
            merge_duration_ms=0  # Will be set by caller
        )
