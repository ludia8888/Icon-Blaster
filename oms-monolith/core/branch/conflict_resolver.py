"""
REQ-OMS-F2-AC3: 충돌 해결 엔진
섹션 8.2의 ConflictResolver 구현
"""
import logging
from typing import Any, Dict, List, Optional

from core.branch.models import (
    Conflict,
    ConflictType,
    DiffEntry,
    ThreeWayDiff,
)

logger = logging.getLogger(__name__)


class ConflictResolver:
    """
    REQ-OMS-F2-AC3: 충돌 감지 및 해결 엔진
    3-way diff 기반 충돌 감지 및 자동 해결
    """

    async def detect_conflicts(self, diff: ThreeWayDiff) -> List[Conflict]:
        """
        REQ-OMS-F2-AC3: 3-way diff에서 충돌 감지
        충돌 종류별 감지 및 분류
        """
        # DiffEngine에서 이미 충돌을 감지했으므로 반환
        return diff.conflicts

    async def apply_resolutions(
        self,
        diff: ThreeWayDiff,
        conflicts: List[Conflict],
        resolutions: Dict[str, Any]
    ) -> ThreeWayDiff:
        """
        REQ-OMS-F2-AC3: 충돌 해결 적용
        사용자 제공 해결방안을 Diff에 적용
        """
        if not resolutions:
            raise ValueError("No conflict resolutions provided")

        resolved_diff = ThreeWayDiff(
            base_commit=diff.base_commit,
            source_commit=diff.source_commit,
            target_commit=diff.target_commit,
            common_ancestor=diff.common_ancestor,
            base_to_source=diff.base_to_source.copy(),
            base_to_target=diff.base_to_target.copy(),
            conflicts=[],  # 해결된 충돌은 제거
            can_auto_merge=True
        )

        # 각 충돌에 대한 해결 적용
        for conflict in conflicts:
            resolution = resolutions.get(conflict.id)
            if not resolution:
                # 해결되지 않은 충돌
                resolved_diff.conflicts.append(conflict)
                resolved_diff.can_auto_merge = False
                continue

            # 해결 방법에 따라 처리
            await self._apply_single_resolution(
                resolved_diff,
                conflict,
                resolution
            )

        return resolved_diff

    async def _apply_single_resolution(
        self,
        diff: ThreeWayDiff,
        conflict: Conflict,
        resolution: Dict[str, Any]
    ):
        """단일 충돌 해결 적용"""
        resolution_type = resolution.get("resolution_type", "use-source")

        if resolution_type == "use-source":
            # 소스 브랜치의 변경사항 사용
            await self._use_source_resolution(diff, conflict)
        elif resolution_type == "use-target":
            # 타겟 브랜치의 변경사항 사용
            await self._use_target_resolution(diff, conflict)
        elif resolution_type == "manual":
            # 수동 해결
            await self._use_manual_resolution(diff, conflict, resolution)
        else:
            raise ValueError(f"Unknown resolution type: {resolution_type}")

    async def _use_source_resolution(
        self,
        diff: ThreeWayDiff,
        conflict: Conflict
    ):
        """소스 브랜치의 변경사항 사용"""
        # 타겟 변경사항에서 충돌된 항목 제거
        diff.base_to_target = [
            entry for entry in diff.base_to_target
            if entry.path != conflict.path
        ]

    async def _use_target_resolution(
        self,
        diff: ThreeWayDiff,
        conflict: Conflict
    ):
        """타겟 브랜치의 변경사항 사용"""
        # 소스 변경사항에서 충돌된 항목 제거
        diff.base_to_source = [
            entry for entry in diff.base_to_source
            if entry.path != conflict.path
        ]

    async def _use_manual_resolution(
        self,
        diff: ThreeWayDiff,
        conflict: Conflict,
        resolution: Dict[str, Any]
    ):
        """수동 해결 적용"""
        resolved_value = resolution.get("resolved_value")
        if not resolved_value:
            raise ValueError("Manual resolution requires resolved_value")

        # 양쪽 변경사항을 수동 해결값으로 대체
        for entries in [diff.base_to_source, diff.base_to_target]:
            for i, entry in enumerate(entries):
                if entry.path == conflict.path:
                    entries[i] = DiffEntry(
                        operation="modify",
                        resource_type=entry.resource_type,
                        resource_id=entry.resource_id,
                        resource_name=entry.resource_name,
                        path=entry.path,
                        old_value=entry.old_value,
                        new_value=resolved_value,
                        metadata={"manually_resolved": True}
                    )

    def analyze_conflict_impact(
        self,
        conflict: Conflict
    ) -> Dict[str, Any]:
        """충돌의 영향도 분석"""
        impact = {
            "severity": "low",
            "affected_resources": [],
            "breaking_change": False,
            "data_loss_risk": False,
            "recommendations": []
        }

        # 충돌 타입별 영향도 분석
        if conflict.conflict_type == ConflictType.MODIFY_DELETE:
            impact["severity"] = "high"
            impact["data_loss_risk"] = True
            impact["recommendations"].append(
                "Consider keeping the resource if it has dependencies"
            )

        elif conflict.conflict_type == ConflictType.MODIFY_MODIFY:
            # 수정 내용에 따라 영향도 결정
            if conflict.resource_type == "Property":
                if self._is_breaking_property_change(
                    conflict.source_value,
                    conflict.target_value
                ):
                    impact["severity"] = "high"
                    impact["breaking_change"] = True
                    impact["recommendations"].append(
                        "This change may break existing data or applications"
                    )
                else:
                    impact["severity"] = "medium"

        elif conflict.conflict_type == ConflictType.ADD_ADD:
            impact["severity"] = "medium"
            impact["recommendations"].append(
                "Merge the definitions or rename one of them"
            )

        return impact

    def _is_breaking_property_change(
        self,
        source_value: Any,
        target_value: Any
    ) -> bool:
        """Property 변경이 breaking change인지 확인"""
        if not isinstance(source_value, dict) or not isinstance(target_value, dict):
            return False

        # Breaking changes:
        # 1. 타입 변경
        if source_value.get("dataTypeId") != target_value.get("dataTypeId"):
            return True

        # 2. Required로 변경
        if source_value.get("isRequired") and not target_value.get("isRequired"):
            return True

        # 3. Unique 제약 추가
        if source_value.get("isUnique") and not target_value.get("isUnique"):
            return True

        return False

    async def suggest_auto_resolution(
        self,
        conflict: Conflict
    ) -> Optional[Dict[str, Any]]:
        """자동 해결 제안"""
        # 간단한 충돌에 대한 자동 해결 제안

        if conflict.conflict_type == ConflictType.ADD_ADD:
            # 같은 내용이면 자동 해결 가능
            if conflict.source_value == conflict.target_value:
                return {
                    "resolution_type": "use-source",
                    "reason": "Both branches added identical content"
                }

        elif conflict.conflict_type == ConflictType.MODIFY_MODIFY:
            # 메타데이터만 다른 경우
            if self._only_metadata_differs(
                conflict.source_value,
                conflict.target_value
            ):
                return {
                    "resolution_type": "use-source",
                    "reason": "Only metadata differs, using latest"
                }

        return None

    def _only_metadata_differs(
        self,
        source: Any,
        target: Any
    ) -> bool:
        """메타데이터만 다른지 확인"""
        if not isinstance(source, dict) or not isinstance(target, dict):
            return False

        # 메타데이터 필드
        metadata_fields = {
            "modifiedAt", "modifiedBy", "versionHash",
            "updatedAt", "updatedBy"
        }

        # 메타데이터 외의 필드 비교
        for key in set(source.keys()) | set(target.keys()):
            if key not in metadata_fields:
                if source.get(key) != target.get(key):
                    return False

        return True

    def create_conflict_report(
        self,
        conflicts: List[Conflict]
    ) -> Dict[str, Any]:
        """충돌 보고서 생성"""
        report = {
            "total_conflicts": len(conflicts),
            "by_type": {},
            "by_resource": {},
            "severity_summary": {
                "high": 0,
                "medium": 0,
                "low": 0
            },
            "auto_resolvable": 0,
            "manual_required": 0
        }

        for conflict in conflicts:
            # 타입별 집계
            conflict_type = conflict.conflict_type.value
            report["by_type"][conflict_type] = \
                report["by_type"].get(conflict_type, 0) + 1

            # 리소스별 집계
            resource_type = conflict.resource_type
            report["by_resource"][resource_type] = \
                report["by_resource"].get(resource_type, 0) + 1

            # 영향도 분석
            impact = self.analyze_conflict_impact(conflict)
            severity = impact["severity"]
            report["severity_summary"][severity] += 1

            # 자동 해결 가능 여부
            if impact.get("auto_resolvable"):
                report["auto_resolvable"] += 1
            else:
                report["manual_required"] += 1

        return report
