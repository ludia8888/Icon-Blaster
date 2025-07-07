"""
REQ-OMS-F2-AC3: 스키마 Diff 계산 엔진
REQ-OMS-F2-AC4: Preview 기능 지원
섹션 8.2.3의 DiffEngine 구현
"""
import logging
import os
from typing import Any, Dict, List, Optional

from core.branch.models import (
    BranchDiff,
    Conflict,
    ConflictType,
    DiffEntry,
    ThreeWayDiff,
)
from database.clients.terminus_db import TerminusDBClient

logger = logging.getLogger(__name__)


class DiffEngine:
    """
    REQ-OMS-F2-AC3: 스키마 Diff 계산 엔진
    REQ-OMS-F2-AC4: 브랜치 간 차이점 계산 및 Preview 지원
    """

    def __init__(self, tdb_endpoint: str):
        self.tdb_endpoint = tdb_endpoint
        self.db_name = os.getenv("TERMINUSDB_DB", "oms")

    async def calculate_branch_diff(
        self,
        source_branch: str,
        target_branch: str,
        format: str = "summary"
    ) -> BranchDiff:
        """
        REQ-OMS-F2-AC4: 브랜치 간 차이점 계산
        머지 Preview 기능을 위한 Diff 엔진
        """
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 현재 TerminusDBClient는 브랜치 정보 조회 메서드가 없으므로 기본값 사용
            source_info = {"head": f"head_{source_branch}", "branch": source_branch}
            target_info = {"head": f"head_{target_branch}", "branch": target_branch}
            
            logger.warning("DiffEngine: get_branch_info not implemented in TerminusDBClient, using mock data")

            # 각 브랜치의 스키마 조회
            source_schema = await self._get_branch_schema(source_branch)
            target_schema = await self._get_branch_schema(target_branch)

            # Diff 계산
            entries = await self._calculate_diff_entries(
                source_schema,
                target_schema,
                format
            )

            # 통계 계산
            additions = len([e for e in entries if e.operation == "add"])
            modifications = len([e for e in entries if e.operation == "modify"])
            deletions = len([e for e in entries if e.operation == "delete"])
            renames = len([e for e in entries if e.operation == "rename"])

            return BranchDiff(
                source_branch=source_branch,
                target_branch=target_branch,
                base_hash=target_info.get("head", ""),
                source_hash=source_info.get("head", ""),
                target_hash=target_info.get("head", ""),
                total_changes=len(entries),
                additions=additions,
                modifications=modifications,
                deletions=deletions,
                renames=renames,
                entries=entries,
                has_conflicts=False,
                conflicts=[]
            )

    async def calculate_three_way_diff(
        self,
        base: str,
        source: str,
        target: str
    ) -> ThreeWayDiff:
        """3-way diff 계산"""
        # 각 커밋의 스키마 조회
        base_schema = await self._get_commit_schema(base) if base else {}
        source_schema = await self._get_commit_schema(source)
        target_schema = await self._get_commit_schema(target)

        # Base -> Source 변경사항
        base_to_source = await self._calculate_diff_entries(
            base_schema,
            source_schema,
            "detailed"
        )

        # Base -> Target 변경사항
        base_to_target = await self._calculate_diff_entries(
            base_schema,
            target_schema,
            "detailed"
        )

        # 충돌 감지
        conflicts = await self._detect_conflicts(
            base_to_source,
            base_to_target,
            base_schema,
            source_schema,
            target_schema
        )

        return ThreeWayDiff(
            base_commit=base,
            source_commit=source,
            target_commit=target,
            common_ancestor=base,  # 간단한 구현
            base_to_source=base_to_source,
            base_to_target=base_to_target,
            conflicts=conflicts,
            can_auto_merge=len(conflicts) == 0
        )

    async def _get_branch_schema(self, branch: str) -> Dict[str, Any]:
        """브랜치의 전체 스키마 조회"""
        schema = {
            "objectTypes": {},
            "linkTypes": {},
            "interfaces": {},
            "sharedProperties": {}
        }

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            logger.warning("DiffEngine: get_all_documents not implemented in TerminusDBClient, returning empty schema")
            
            # TODO: 실제 WOQL 쿼리를 사용하여 문서 조회 구현 필요
            # 현재는 빈 스키마 반환
            # 
            # 예시 WOQL 쿼리:
            # woql_query = {
            #     "@type": "Select",
            #     "variables": ["doc"],
            #     "query": {
            #         "@type": "Triple",
            #         "subject": {"@type": "Variable", "name": "doc"},
            #         "predicate": {"@type": "NodeValue", "node": "rdf:type"},
            #         "object": {"@type": "Value", "data": {"@type": "xsd:string", "@value": "ObjectType"}}
            #     }
            # }
            # result = await tdb.query(self.db_name, woql_query)

        return schema

    async def _get_commit_schema(self, commit_hash: str) -> Dict[str, Any]:
        """특정 커밋의 스키마 조회"""
        # TODO: 커밋 기반 스키마 조회 구현
        # 현재는 브랜치 스키마를 반환
        return await self._get_branch_schema("main")

    async def _calculate_diff_entries(
        self,
        source_schema: Dict[str, Any],
        target_schema: Dict[str, Any],
        format: str
    ) -> List[DiffEntry]:
        """스키마 간 차이점 계산"""
        entries = []

        # ObjectType 차이점
        entries.extend(
            await self._diff_object_types(
                source_schema.get("objectTypes", {}),
                target_schema.get("objectTypes", {}),
                format
            )
        )

        # LinkType 차이점
        entries.extend(
            await self._diff_link_types(
                source_schema.get("linkTypes", {}),
                target_schema.get("linkTypes", {}),
                format
            )
        )

        # Interface 차이점
        entries.extend(
            await self._diff_interfaces(
                source_schema.get("interfaces", {}),
                target_schema.get("interfaces", {}),
                format
            )
        )

        return entries

    async def _diff_object_types(
        self,
        source_types: Dict[str, Any],
        target_types: Dict[str, Any],
        format: str
    ) -> List[DiffEntry]:
        """ObjectType 차이점 계산"""
        entries = []

        # 추가된 타입
        for name in set(source_types) - set(target_types):
            entries.append(DiffEntry(
                operation="add",
                resource_type="ObjectType",
                resource_id=source_types[name].get("id", name),
                resource_name=name,
                path=f"/object_types/{name}",
                old_value=None,
                new_value=source_types[name] if format == "detailed" else None
            ))

        # 삭제된 타입
        for name in set(target_types) - set(source_types):
            entries.append(DiffEntry(
                operation="delete",
                resource_type="ObjectType",
                resource_id=target_types[name].get("id", name),
                resource_name=name,
                path=f"/object_types/{name}",
                old_value=target_types[name] if format == "detailed" else None,
                new_value=None
            ))

        # 수정된 타입
        for name in set(source_types) & set(target_types):
            source_type = source_types[name]
            target_type = target_types[name]

            # 버전 해시로 변경 감지
            if source_type.get("versionHash") != target_type.get("versionHash"):
                # 세부 변경사항 분석
                changes = self._analyze_object_type_changes(
                    source_type,
                    target_type,
                    format
                )

                if changes:
                    entries.append(DiffEntry(
                        operation="modify",
                        resource_type="ObjectType",
                        resource_id=source_type.get("id", name),
                        resource_name=name,
                        path=f"/object_types/{name}",
                        old_value=target_type if format == "detailed" else None,
                        new_value=source_type if format == "detailed" else None,
                        metadata={"changes": changes} if format != "summary" else None
                    ))

                # Property 차이점도 확인
                prop_entries = await self._diff_properties(
                    name,
                    source_type.get("properties", []),
                    target_type.get("properties", []),
                    format
                )
                entries.extend(prop_entries)

        return entries

    async def _diff_properties(
        self,
        object_type_name: str,
        source_props: List[Dict[str, Any]],
        target_props: List[Dict[str, Any]],
        format: str
    ) -> List[DiffEntry]:
        """Property 차이점 계산"""
        entries = []

        # Property를 이름으로 인덱싱
        source_by_name = {p.get("name"): p for p in source_props}
        target_by_name = {p.get("name"): p for p in target_props}

        # 추가된 속성
        for name in set(source_by_name) - set(target_by_name):
            entries.append(DiffEntry(
                operation="add",
                resource_type="Property",
                resource_id=source_by_name[name].get("id", name),
                resource_name=name,
                path=f"/object_types/{object_type_name}/properties/{name}",
                old_value=None,
                new_value=source_by_name[name] if format == "detailed" else None
            ))

        # 삭제된 속성
        for name in set(target_by_name) - set(source_by_name):
            entries.append(DiffEntry(
                operation="delete",
                resource_type="Property",
                resource_id=target_by_name[name].get("id", name),
                resource_name=name,
                path=f"/object_types/{object_type_name}/properties/{name}",
                old_value=target_by_name[name] if format == "detailed" else None,
                new_value=None
            ))

        # 수정된 속성
        for name in set(source_by_name) & set(target_by_name):
            source_prop = source_by_name[name]
            target_prop = target_by_name[name]

            changes = self._analyze_property_changes(source_prop, target_prop)
            if changes:
                entries.append(DiffEntry(
                    operation="modify",
                    resource_type="Property",
                    resource_id=source_prop.get("id", name),
                    resource_name=name,
                    path=f"/object_types/{object_type_name}/properties/{name}",
                    old_value=target_prop if format == "detailed" else None,
                    new_value=source_prop if format == "detailed" else None,
                    metadata={"changes": changes} if format != "summary" else None
                ))

        return entries

    async def _diff_link_types(
        self,
        source_links: Dict[str, Any],
        target_links: Dict[str, Any],
        format: str
    ) -> List[DiffEntry]:
        """LinkType 차이점 계산"""
        entries = []

        # 추가된 링크
        for name in set(source_links) - set(target_links):
            entries.append(DiffEntry(
                operation="add",
                resource_type="LinkType",
                resource_id=source_links[name].get("id", name),
                resource_name=name,
                path=f"/link_types/{name}",
                old_value=None,
                new_value=source_links[name] if format == "detailed" else None
            ))

        # 삭제된 링크
        for name in set(target_links) - set(source_links):
            entries.append(DiffEntry(
                operation="delete",
                resource_type="LinkType",
                resource_id=target_links[name].get("id", name),
                resource_name=name,
                path=f"/link_types/{name}",
                old_value=target_links[name] if format == "detailed" else None,
                new_value=None
            ))

        # 수정된 링크
        for name in set(source_links) & set(target_links):
            source_link = source_links[name]
            target_link = target_links[name]

            if source_link.get("versionHash") != target_link.get("versionHash"):
                entries.append(DiffEntry(
                    operation="modify",
                    resource_type="LinkType",
                    resource_id=source_link.get("id", name),
                    resource_name=name,
                    path=f"/link_types/{name}",
                    old_value=target_link if format == "detailed" else None,
                    new_value=source_link if format == "detailed" else None
                ))

        return entries

    async def _diff_interfaces(
        self,
        source_interfaces: Dict[str, Any],
        target_interfaces: Dict[str, Any],
        format: str
    ) -> List[DiffEntry]:
        """Interface 차이점 계산"""
        entries = []

        # 추가된 인터페이스
        for name in set(source_interfaces) - set(target_interfaces):
            entries.append(DiffEntry(
                operation="add",
                resource_type="Interface",
                resource_id=source_interfaces[name].get("id", name),
                resource_name=name,
                path=f"/interfaces/{name}",
                old_value=None,
                new_value=source_interfaces[name] if format == "detailed" else None
            ))

        # 삭제된 인터페이스
        for name in set(target_interfaces) - set(source_interfaces):
            entries.append(DiffEntry(
                operation="delete",
                resource_type="Interface",
                resource_id=target_interfaces[name].get("id", name),
                resource_name=name,
                path=f"/interfaces/{name}",
                old_value=target_interfaces[name] if format == "detailed" else None,
                new_value=None
            ))

        # 수정된 인터페이스
        for name in set(source_interfaces) & set(target_interfaces):
            source_intf = source_interfaces[name]
            target_intf = target_interfaces[name]

            if source_intf.get("versionHash") != target_intf.get("versionHash"):
                entries.append(DiffEntry(
                    operation="modify",
                    resource_type="Interface",
                    resource_id=source_intf.get("id", name),
                    resource_name=name,
                    path=f"/interfaces/{name}",
                    old_value=target_intf if format == "detailed" else None,
                    new_value=source_intf if format == "detailed" else None
                ))

        return entries

    def _analyze_object_type_changes(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any],
        format: str
    ) -> List[Dict[str, Any]]:
        """ObjectType의 세부 변경사항 분석"""
        changes = []

        # 비교할 필드들
        fields = [
            "displayName", "pluralDisplayName", "description",
            "status", "typeClass", "icon", "color",
            "titleProperty", "subtitleProperty", "docUrl"
        ]

        for field in fields:
            if source.get(field) != target.get(field):
                changes.append({
                    "field": field,
                    "old": target.get(field),
                    "new": source.get(field)
                })

        # 인터페이스 변경
        source_interfaces = set(source.get("baseInterfaces", []))
        target_interfaces = set(target.get("baseInterfaces", []))

        if source_interfaces != target_interfaces:
            changes.append({
                "field": "baseInterfaces",
                "added": list(source_interfaces - target_interfaces),
                "removed": list(target_interfaces - source_interfaces)
            })

        return changes

    def _analyze_property_changes(
        self,
        source: Dict[str, Any],
        target: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Property의 세부 변경사항 분석"""
        changes = []

        # 비교할 필드들
        fields = [
            "displayName", "description", "dataTypeId",
            "isRequired", "isPrimaryKey", "isIndexed",
            "isUnique", "isSearchable", "defaultValue",
            "sortOrder", "visibility"
        ]

        for field in fields:
            if source.get(field) != target.get(field):
                changes.append({
                    "field": field,
                    "old": target.get(field),
                    "new": source.get(field)
                })

        return changes

    async def _detect_conflicts(
        self,
        base_to_source: List[DiffEntry],
        base_to_target: List[DiffEntry],
        base_schema: Dict[str, Any],
        source_schema: Dict[str, Any],
        target_schema: Dict[str, Any]
    ) -> List[Conflict]:
        """충돌 감지"""
        conflicts = []

        # 경로별로 변경사항 그룹화
        source_changes = {e.path: e for e in base_to_source}
        target_changes = {e.path: e for e in base_to_target}

        # 같은 경로에 대한 변경 확인
        for path in set(source_changes) & set(target_changes):
            source_entry = source_changes[path]
            target_entry = target_changes[path]

            conflict = self._check_conflict(
                source_entry,
                target_entry,
                base_schema,
                source_schema,
                target_schema
            )

            if conflict:
                conflicts.append(conflict)

        return conflicts

    def _check_conflict(
        self,
        source_entry: DiffEntry,
        target_entry: DiffEntry,
        base_schema: Dict[str, Any],
        source_schema: Dict[str, Any],
        target_schema: Dict[str, Any]
    ) -> Optional[Conflict]:
        """두 변경사항 간 충돌 확인"""

        # 양쪽 모두 수정
        if source_entry.operation == "modify" and target_entry.operation == "modify":
            # 같은 필드를 다르게 수정했는지 확인
            if source_entry.new_value != target_entry.new_value:
                return Conflict(
                    id=f"conflict_{source_entry.resource_id}",
                    conflict_type=ConflictType.MODIFY_MODIFY,
                    resource_type=source_entry.resource_type,
                    resource_id=source_entry.resource_id,
                    resource_name=source_entry.resource_name,
                    base_value=source_entry.old_value,
                    source_value=source_entry.new_value,
                    target_value=target_entry.new_value,
                    path=source_entry.path,
                    description=f"Both branches modified {source_entry.resource_name}"
                )

        # 한쪽은 수정, 한쪽은 삭제
        elif (source_entry.operation == "modify" and target_entry.operation == "delete") or \
             (source_entry.operation == "delete" and target_entry.operation == "modify"):
            return Conflict(
                id=f"conflict_{source_entry.resource_id}",
                conflict_type=ConflictType.MODIFY_DELETE,
                resource_type=source_entry.resource_type,
                resource_id=source_entry.resource_id,
                resource_name=source_entry.resource_name,
                base_value=source_entry.old_value or target_entry.old_value,
                source_value=source_entry.new_value,
                target_value=target_entry.new_value,
                path=source_entry.path,
                description=f"One branch modified while other deleted {source_entry.resource_name}"
            )

        # 양쪽에서 같은 이름으로 추가
        elif source_entry.operation == "add" and target_entry.operation == "add":
            if source_entry.new_value != target_entry.new_value:
                return Conflict(
                    id=f"conflict_{source_entry.resource_id}",
                    conflict_type=ConflictType.ADD_ADD,
                    resource_type=source_entry.resource_type,
                    resource_id=source_entry.resource_id,
                    resource_name=source_entry.resource_name,
                    base_value=None,
                    source_value=source_entry.new_value,
                    target_value=target_entry.new_value,
                    path=source_entry.path,
                    description=f"Both branches added {source_entry.resource_name} with different values"
                )

        return None
