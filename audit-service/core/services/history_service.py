"""
History Service (Migrated from OMS)
OMS core/history/service.py에서 이관된 히스토리 조회/관리 로직
"""
import asyncio
import csv
import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from models.history import (
    HistoryQuery, HistoryListResponse, HistoryEntry, CommitDetail,
    ChangeDetail, AffectedResource, ResourceType, ChangeOperation
)
from core.repositories.history_repository import HistoryRepository
from utils.logger import get_logger

logger = get_logger(__name__)


class HistoryService:
    """
    History Service (OMS에서 이관)
    스키마 변경 히스토리 조회/관리 전담 서비스
    """
    
    def __init__(self, history_repository: Optional[HistoryRepository] = None):
        self.history_repository = history_repository or HistoryRepository()
    
    async def list_history(
        self,
        query: HistoryQuery,
        user_context: Dict[str, Any]
    ) -> HistoryListResponse:
        """
        스키마 변경 히스토리 목록 조회 (OMS에서 이관)
        """
        logger.info(f"Listing history with query: {query.dict()}")
        
        try:
            start_time = datetime.now()
            
            # 권한 기반 필터링
            query = await self._apply_access_filters(query, user_context)
            
            # 히스토리 엔트리 조회
            entries, total_count, has_more, next_cursor = await self.history_repository.search_history(
                query
            )
            
            # 요약 통계 생성
            summary = await self._generate_summary_statistics(entries, query)
            
            # 적용된 필터 정보
            applied_filters = self._get_applied_filters(query)
            
            query_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return HistoryListResponse(
                entries=entries,
                total_count=total_count,
                has_more=has_more,
                next_cursor=next_cursor,
                query_time_ms=query_time_ms,
                applied_filters=applied_filters,
                summary=summary
            )
            
        except Exception as e:
            logger.error(f"Failed to list history: {str(e)}")
            raise
    
    async def get_commit_detail(
        self,
        commit_hash: str,
        branch: str,
        include_snapshot: bool = False,
        include_changes: bool = True,
        include_affected: bool = True,
        user_context: Dict[str, Any]
    ) -> Optional[CommitDetail]:
        """
        커밋 상세 정보 조회 (OMS에서 이관)
        """
        logger.info(f"Getting commit detail: {commit_hash} on {branch}")
        
        try:
            # 권한 확인
            if not await self._has_access_to_branch(branch, user_context):
                raise PermissionError(f"No access to branch {branch}")
            
            start_time = datetime.now()
            
            # 커밋 기본 정보 조회
            commit_detail = await self.history_repository.get_commit_by_hash(
                commit_hash, branch
            )
            
            if not commit_detail:
                return None
            
            # 상세 변경 내역 조회
            if include_changes:
                detailed_changes = await self.history_repository.get_commit_changes(
                    commit_hash, branch
                )
                commit_detail.detailed_changes = detailed_changes
            
            # 영향받은 리소스 조회
            if include_affected:
                affected_resources = await self.history_repository.get_affected_resources(
                    commit_hash, branch
                )
                commit_detail.affected_resources = affected_resources
                
                # 영향 분석 수행
                commit_detail.impact_analysis = await self._analyze_impact(
                    affected_resources, detailed_changes
                )
            
            # 스키마 스냅샷 조회 (선택적)
            if include_snapshot:
                snapshot = await self.history_repository.get_schema_snapshot(
                    commit_hash, branch
                )
                commit_detail.snapshot = snapshot
                
                if snapshot:
                    commit_detail.snapshot_size_bytes = len(json.dumps(snapshot).encode())
            
            # 생성 시간 기록
            generation_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            commit_detail.generation_time_ms = generation_time_ms
            
            return commit_detail
            
        except Exception as e:
            logger.error(f"Failed to get commit detail: {str(e)}")
            raise
    
    async def get_commit_diff(
        self,
        commit_hash: str,
        compare_with: Optional[str] = None,
        branch: str = "main",
        format: str = "json",
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """커밋 간 차이점 조회"""
        logger.info(f"Getting diff for {commit_hash} vs {compare_with} on {branch}")
        
        try:
            # 권한 확인
            if not await self._has_access_to_branch(branch, user_context):
                raise PermissionError(f"No access to branch {branch}")
            
            # 비교 대상 결정 (기본값: 이전 커밋)
            if not compare_with:
                compare_with = await self.history_repository.get_previous_commit(
                    commit_hash, branch
                )
            
            # 두 커밋의 스키마 조회
            current_schema = await self.history_repository.get_schema_snapshot(
                commit_hash, branch
            )
            previous_schema = await self.history_repository.get_schema_snapshot(
                compare_with, branch
            )
            
            # 차이점 분석
            diff_result = await self._compute_schema_diff(
                previous_schema, current_schema, format
            )
            
            return {
                "commit_hash": commit_hash,
                "compare_with": compare_with,
                "branch": branch,
                "format": format,
                "diff": diff_result,
                "generated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate diff: {str(e)}")
            raise
    
    async def get_statistics(
        self,
        branch: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        group_by: str = "day",
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """히스토리 통계 조회"""
        logger.info(f"Getting statistics: branch={branch}, group_by={group_by}")
        
        try:
            # 통계 데이터 조회
            stats = await self.history_repository.get_statistics(
                branch=branch,
                from_date=from_date,
                to_date=to_date,
                group_by=group_by
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {str(e)}")
            raise
    
    async def export_history(
        self,
        format: str = "csv",
        branch: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        include_changes: bool = False,
        user_context: Dict[str, Any]
    ) -> Tuple[io.BytesIO, str, str]:
        """히스토리 데이터 내보내기"""
        logger.info(f"Exporting history: format={format}, branch={branch}")
        
        try:
            # 권한 확인
            if not await self._has_export_permission(user_context):
                raise PermissionError("No export permission")
            
            # 내보낼 데이터 조회
            query = HistoryQuery(
                branch=branch,
                from_date=from_date,
                to_date=to_date,
                include_changes=include_changes,
                limit=10000  # 대량 내보내기
            )
            
            entries, _, _, _ = await self.history_repository.search_history(query)
            
            # 형식에 따른 파일 생성
            if format.lower() == "csv":
                return await self._export_to_csv(entries, include_changes)
            elif format.lower() == "json":
                return await self._export_to_json(entries)
            elif format.lower() == "xlsx":
                return await self._export_to_excel(entries, include_changes)
            else:
                raise ValueError(f"Unsupported export format: {format}")
            
        except Exception as e:
            logger.error(f"Failed to export history: {str(e)}")
            raise
    
    # Private methods
    
    async def _apply_access_filters(
        self,
        query: HistoryQuery,
        user_context: Dict[str, Any]
    ) -> HistoryQuery:
        """사용자 권한에 따른 필터 적용"""
        # TODO: 실제 권한 시스템과 연동
        user_branches = user_context.get("accessible_branches", ["main"])
        
        if query.branch and query.branch not in user_branches:
            raise PermissionError(f"No access to branch {query.branch}")
        
        return query
    
    async def _has_access_to_branch(
        self,
        branch: str,
        user_context: Dict[str, Any]
    ) -> bool:
        """브랜치 접근 권한 확인"""
        accessible_branches = user_context.get("accessible_branches", ["main"])
        return branch in accessible_branches
    
    async def _has_export_permission(self, user_context: Dict[str, Any]) -> bool:
        """내보내기 권한 확인"""
        permissions = user_context.get("permissions", [])
        return "history:export" in permissions or "audit:export" in permissions
    
    async def _generate_summary_statistics(
        self,
        entries: List[HistoryEntry],
        query: HistoryQuery
    ) -> Dict[str, Any]:
        """요약 통계 생성"""
        if not entries:
            return {}
        
        operations = {}
        resource_types = {}
        breaking_changes = 0
        
        for entry in entries:
            # 작업 타입별 집계
            op = entry.operation.value
            operations[op] = operations.get(op, 0) + 1
            
            # 리소스 타입별 집계
            rt = entry.resource_type.value
            resource_types[rt] = resource_types.get(rt, 0) + 1
            
            # Breaking change 집계
            breaking_changes += entry.breaking_changes
        
        return {
            "total_entries": len(entries),
            "operations": operations,
            "resource_types": resource_types,
            "breaking_changes": breaking_changes,
            "time_range": {
                "from": query.from_date.isoformat() if query.from_date else None,
                "to": query.to_date.isoformat() if query.to_date else None
            }
        }
    
    def _get_applied_filters(self, query: HistoryQuery) -> Dict[str, Any]:
        """적용된 필터 정보 반환"""
        filters = {}
        
        if query.branch:
            filters["branch"] = query.branch
        if query.resource_type:
            filters["resource_type"] = query.resource_type.value
        if query.resource_id:
            filters["resource_id"] = query.resource_id
        if query.author:
            filters["author"] = query.author
        if query.operation:
            filters["operation"] = query.operation.value
        if query.from_date:
            filters["from_date"] = query.from_date.isoformat()
        if query.to_date:
            filters["to_date"] = query.to_date.isoformat()
        
        return filters
    
    async def _analyze_impact(
        self,
        affected_resources: List[AffectedResource],
        changes: List[ChangeDetail]
    ) -> Dict[str, Any]:
        """영향 분석 수행"""
        if not affected_resources:
            return {}
        
        # 영향도별 집계
        impact_by_severity = {}
        impact_by_type = {}
        
        for resource in affected_resources:
            severity = resource.impact_severity
            impact_by_severity[severity] = impact_by_severity.get(severity, 0) + 1
            
            impact_type = resource.impact_type
            impact_by_type[impact_type] = impact_by_type.get(impact_type, 0) + 1
        
        # Breaking change 분석
        breaking_changes = [c for c in changes if c.breaking_change]
        
        return {
            "total_affected": len(affected_resources),
            "impact_by_severity": impact_by_severity,
            "impact_by_type": impact_by_type,
            "breaking_changes_count": len(breaking_changes),
            "risk_assessment": self._assess_risk_level(impact_by_severity, len(breaking_changes))
        }
    
    def _assess_risk_level(
        self,
        impact_by_severity: Dict[str, int],
        breaking_changes: int
    ) -> str:
        """위험 수준 평가"""
        critical = impact_by_severity.get("critical", 0)
        high = impact_by_severity.get("high", 0)
        
        if critical > 0 or breaking_changes > 0:
            return "critical"
        elif high > 0:
            return "high"
        elif impact_by_severity.get("medium", 0) > 0:
            return "medium"
        else:
            return "low"
    
    async def _compute_schema_diff(
        self,
        previous_schema: Dict[str, Any],
        current_schema: Dict[str, Any],
        format: str
    ) -> Union[Dict[str, Any], str]:
        """스키마 차이점 계산"""
        if format == "json":
            return self._compute_json_diff(previous_schema, current_schema)
        elif format == "text":
            return self._compute_text_diff(previous_schema, current_schema)
        elif format == "unified":
            return self._compute_unified_diff(previous_schema, current_schema)
        else:
            raise ValueError(f"Unsupported diff format: {format}")
    
    def _compute_json_diff(
        self,
        previous: Dict[str, Any],
        current: Dict[str, Any]
    ) -> Dict[str, Any]:
        """JSON 형식 차이점 계산"""
        # 간단한 차이점 분석 (실제로는 더 정교한 알고리즘 필요)
        diff = {
            "added": {},
            "removed": {},
            "modified": {}
        }
        
        # 추가된 항목
        for key in current:
            if key not in previous:
                diff["added"][key] = current[key]
        
        # 제거된 항목
        for key in previous:
            if key not in current:
                diff["removed"][key] = previous[key]
        
        # 수정된 항목
        for key in current:
            if key in previous and current[key] != previous[key]:
                diff["modified"][key] = {
                    "before": previous[key],
                    "after": current[key]
                }
        
        return diff
    
    def _compute_text_diff(
        self,
        previous: Dict[str, Any],
        current: Dict[str, Any]
    ) -> str:
        """텍스트 형식 차이점 계산"""
        # 간단한 텍스트 차이점 표현
        lines = []
        
        for key in sorted(set(previous.keys()) | set(current.keys())):
            if key not in previous:
                lines.append(f"+ {key}: {current[key]}")
            elif key not in current:
                lines.append(f"- {key}: {previous[key]}")
            elif previous[key] != current[key]:
                lines.append(f"- {key}: {previous[key]}")
                lines.append(f"+ {key}: {current[key]}")
        
        return "\\n".join(lines)
    
    def _compute_unified_diff(
        self,
        previous: Dict[str, Any],
        current: Dict[str, Any]
    ) -> str:
        """Unified diff 형식 계산"""
        import difflib
        
        prev_lines = json.dumps(previous, indent=2, sort_keys=True).splitlines()
        curr_lines = json.dumps(current, indent=2, sort_keys=True).splitlines()
        
        diff = difflib.unified_diff(
            prev_lines,
            curr_lines,
            fromfile="previous",
            tofile="current",
            lineterm=""
        )
        
        return "\\n".join(diff)
    
    async def _export_to_csv(
        self,
        entries: List[HistoryEntry],
        include_changes: bool
    ) -> Tuple[io.BytesIO, str, str]:
        """CSV 형식으로 내보내기"""
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 헤더
        headers = [
            "commit_hash", "branch", "timestamp", "author", "message",
            "operation", "resource_type", "resource_id", "total_changes"
        ]
        if include_changes:
            headers.extend(["change_details"])
        
        writer.writerow(headers)
        
        # 데이터
        for entry in entries:
            row = [
                entry.commit_hash,
                entry.branch,
                entry.timestamp.isoformat(),
                entry.author,
                entry.message,
                entry.operation.value,
                entry.resource_type.value,
                entry.resource_id,
                entry.total_changes
            ]
            
            if include_changes:
                changes_json = json.dumps([c.dict() for c in entry.changes])
                row.append(changes_json)
            
            writer.writerow(row)
        
        # BytesIO로 변환
        csv_content = output.getvalue()
        bytes_output = io.BytesIO(csv_content.encode('utf-8'))
        
        filename = f"history_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return bytes_output, filename, "text/csv"
    
    async def _export_to_json(
        self,
        entries: List[HistoryEntry]
    ) -> Tuple[io.BytesIO, str, str]:
        """JSON 형식으로 내보내기"""
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_entries": len(entries),
            "entries": [entry.dict() for entry in entries]
        }
        
        json_content = json.dumps(data, indent=2, default=str)
        bytes_output = io.BytesIO(json_content.encode('utf-8'))
        
        filename = f"history_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        return bytes_output, filename, "application/json"
    
    async def _export_to_excel(
        self,
        entries: List[HistoryEntry],
        include_changes: bool
    ) -> Tuple[io.BytesIO, str, str]:
        """Excel 형식으로 내보내기"""
        # pandas/openpyxl을 사용한 Excel 내보내기
        # 실제 구현에서는 해당 라이브러리 필요
        
        # 임시로 CSV와 동일한 내용을 반환
        return await self._export_to_csv(entries, include_changes)