"""
Audit Service
감사 로그 검색, 내보내기, 관리 서비스
"""
import asyncio
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from models.audit import (
    AuditSearchQuery, AuditSearchResponse, AuditLogEntry,
    AuditExportRequest, AuditExportResponse
)
from utils.logger import get_logger, log_operation_start, log_operation_end

logger = get_logger(__name__)


class AuditService:
    """
    감사 로그 서비스
    감사 로그 검색, 내보내기, 대시보드 통계 제공
    """
    
    def __init__(self):
        # TODO: 실제 구현에서는 repository 주입
        pass
    
    async def search_logs(
        self,
        query: AuditSearchQuery,
        user_context: Dict[str, Any]
    ) -> AuditSearchResponse:
        """감사 로그 검색"""
        log_operation_start(logger, "search_audit_logs", user_id=user_context.get("user_id"))
        
        try:
            start_time = datetime.now()
            
            # 권한 기반 필터링
            filtered_query = await self._apply_access_filters(query, user_context)
            
            # 감사 로그 검색 (더미 구현)
            entries = await self._search_audit_entries(filtered_query)
            
            # 집계 정보 생성
            aggregations = None
            if query.include_aggregations:
                aggregations = await self._generate_aggregations(entries, query)
            
            # 요약 통계
            summary = self._generate_summary(entries, query)
            
            query_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            response = AuditSearchResponse(
                entries=entries[:query.limit],
                total_count=len(entries),
                has_more=len(entries) > query.limit,
                query_time_ms=query_time_ms,
                applied_filters=self._get_applied_filters(query),
                aggregations=aggregations,
                summary=summary
            )
            
            log_operation_end(logger, "search_audit_logs", success=True, 
                            results_count=len(entries))
            
            return response
            
        except Exception as e:
            log_operation_end(logger, "search_audit_logs", success=False, error=str(e))
            logger.error(f"Failed to search audit logs: {str(e)}")
            raise
    
    async def get_log_details(
        self,
        log_id: str,
        user_context: Dict[str, Any],
        include_metadata: bool = True,
        include_states: bool = False
    ) -> Optional[AuditLogEntry]:
        """감사 로그 상세 조회"""
        try:
            # 더미 구현 - 실제로는 데이터베이스에서 조회
            audit_log = AuditLogEntry(
                log_id=log_id,
                timestamp=datetime.now(timezone.utc),
                event_type="schema_change",
                user_id="user123",
                action="get_log_details",
                resource_type="AuditLog",
                resource_id=log_id
            )
            
            return audit_log
            
        except Exception as e:
            logger.error(f"Failed to get log details: {str(e)}")
            raise
    
    async def start_export(
        self,
        export_request: AuditExportRequest,
        user_context: Dict[str, Any]
    ) -> AuditExportResponse:
        """감사 로그 내보내기 시작"""
        try:
            export_id = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # 내보내기 작업 생성
            export_response = AuditExportResponse(
                export_id=export_id,
                status="pending",
                created_at=datetime.now(timezone.utc),
                total_records=None,
                processed_records=0,
                progress_percentage=0.0
            )
            
            # 백그라운드에서 내보내기 처리 (실제로는 Celery 등 사용)
            asyncio.create_task(self._process_export(export_id, export_request, user_context))
            
            return export_response
            
        except Exception as e:
            logger.error(f"Failed to start export: {str(e)}")
            raise
    
    async def get_export_status(
        self,
        export_id: str,
        user_context: Dict[str, Any]
    ) -> Optional[AuditExportResponse]:
        """내보내기 상태 조회"""
        try:
            # 더미 구현
            return AuditExportResponse(
                export_id=export_id,
                status="completed",
                created_at=datetime.now(timezone.utc),
                total_records=1000,
                processed_records=1000,
                progress_percentage=100.0,
                download_url=f"https://audit-service.com/exports/{export_id}/download",
                file_size_bytes=1024*1024,
                expires_at=datetime.now(timezone.utc)
            )
            
        except Exception as e:
            logger.error(f"Failed to get export status: {str(e)}")
            raise
    
    async def download_export(
        self,
        export_id: str,
        user_context: Dict[str, Any]
    ) -> Tuple[io.BytesIO, str, str]:
        """내보낸 파일 다운로드"""
        try:
            # 더미 CSV 파일 생성
            csv_content = "log_id,timestamp,user_id,action,resource_type\\n"
            csv_content += "test_123,2025-06-25T10:30:00Z,user123,test_action,ObjectType\\n"
            
            file_stream = io.BytesIO(csv_content.encode('utf-8'))
            filename = f"audit_export_{export_id}.csv"
            media_type = "text/csv"
            
            return file_stream, filename, media_type
            
        except Exception as e:
            logger.error(f"Failed to download export: {str(e)}")
            raise
    
    async def get_dashboard_statistics(
        self,
        time_range: str = "24h",
        include_trends: bool = True,
        include_top_users: bool = True,
        include_top_actions: bool = True,
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """대시보드 통계 조회"""
        try:
            # 더미 통계 데이터
            stats = {
                "summary": {
                    "total_events": 15000,
                    "unique_users": 45,
                    "success_rate": 0.96,
                    "critical_events": 2,
                    "time_range": time_range
                },
                "event_distribution": {
                    "schema_change": 8000,
                    "user_login": 3000,
                    "data_access": 2500,
                    "api_access": 1500
                },
                "severity_distribution": {
                    "info": 12000,
                    "warning": 2500,
                    "error": 450,
                    "critical": 50
                }
            }
            
            if include_trends:
                stats["trends"] = {
                    "hourly_events": [120, 95, 110, 140, 160, 180],
                    "success_rate_trend": [0.95, 0.96, 0.97, 0.96, 0.95, 0.96]
                }
            
            if include_top_users:
                stats["top_users"] = [
                    {"user_id": "user123", "events": 245},
                    {"user_id": "user456", "events": 189},
                    {"user_id": "user789", "events": 156}
                ]
            
            if include_top_actions:
                stats["top_actions"] = [
                    {"action": "update_object_type", "count": 450},
                    {"action": "user_login", "count": 380},
                    {"action": "data_export", "count": 120}
                ]
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get dashboard statistics: {str(e)}")
            raise
    
    async def get_retention_status(
        self,
        compliance_standard: Optional[str] = None,
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """데이터 보존 상태 조회"""
        try:
            # 더미 보존 상태
            return {
                "total_logs": 150000,
                "retention_policies": [
                    {
                        "standard": "SOX",
                        "retention_days": 2555,
                        "logs_count": 80000,
                        "oldest_log": "2018-01-01T00:00:00Z"
                    },
                    {
                        "standard": "GDPR", 
                        "retention_days": 1095,
                        "logs_count": 45000,
                        "oldest_log": "2022-01-01T00:00:00Z"
                    }
                ],
                "storage_usage": {
                    "total_size_gb": 125.5,
                    "growth_rate_gb_per_month": 8.2,
                    "projected_size_gb_next_year": 223.9
                },
                "cleanup_status": {
                    "last_cleanup": "2025-06-24T02:00:00Z",
                    "next_cleanup": "2025-06-25T02:00:00Z",
                    "expired_logs_pending": 1250
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get retention status: {str(e)}")
            raise
    
    # Private methods
    
    async def _apply_access_filters(
        self,
        query: AuditSearchQuery,
        user_context: Dict[str, Any]
    ) -> AuditSearchQuery:
        """사용자 권한에 따른 필터 적용"""
        # TODO: 실제 권한 시스템과 연동
        return query
    
    async def _search_audit_entries(
        self,
        query: AuditSearchQuery
    ) -> List[AuditLogEntry]:
        """감사 로그 엔트리 검색 (더미 구현)"""
        # 더미 데이터 생성
        entries = []
        for i in range(min(query.limit * 2, 100)):  # 더 많은 결과 시뮬레이션
            entry = AuditLogEntry(
                log_id=f"audit_{i:04d}",
                timestamp=datetime.now(timezone.utc),
                event_type="schema_change",
                user_id=f"user{i % 10}",
                action="update_object_type",
                resource_type="ObjectType",
                resource_id=f"Product_{i}"
            )
            entries.append(entry)
        
        return entries
    
    async def _generate_aggregations(
        self,
        entries: List[AuditLogEntry],
        query: AuditSearchQuery
    ) -> Dict[str, Any]:
        """집계 정보 생성"""
        aggregations = {}
        
        if "event_type" in (query.aggregation_fields or []):
            event_types = {}
            for entry in entries:
                event_type = entry.event_type.value
                event_types[event_type] = event_types.get(event_type, 0) + 1
            aggregations["by_event_type"] = event_types
        
        if "user_id" in (query.aggregation_fields or []):
            users = {}
            for entry in entries:
                user_id = entry.user_id
                users[user_id] = users.get(user_id, 0) + 1
            aggregations["by_user"] = dict(list(users.items())[:10])  # Top 10
        
        return aggregations
    
    def _generate_summary(
        self,
        entries: List[AuditLogEntry],
        query: AuditSearchQuery
    ) -> Dict[str, Any]:
        """요약 통계 생성"""
        if not entries:
            return {}
        
        event_types = {}
        severity_levels = {}
        users = set()
        
        for entry in entries:
            # 이벤트 타입별 집계
            event_type = entry.event_type.value
            event_types[event_type] = event_types.get(event_type, 0) + 1
            
            # 심각도별 집계
            severity = entry.severity.value
            severity_levels[severity] = severity_levels.get(severity, 0) + 1
            
            # 고유 사용자
            users.add(entry.user_id)
        
        return {
            "total_entries": len(entries),
            "event_types": event_types,
            "severity_levels": severity_levels,
            "unique_users": len(users),
            "time_range": {
                "from": query.from_date.isoformat() if query.from_date else None,
                "to": query.to_date.isoformat() if query.to_date else None
            }
        }
    
    def _get_applied_filters(self, query: AuditSearchQuery) -> Dict[str, Any]:
        """적용된 필터 정보"""
        filters = {}
        
        if query.user_id:
            filters["user_id"] = query.user_id
        if query.event_type:
            filters["event_type"] = query.event_type.value
        if query.severity:
            filters["severity"] = query.severity.value
        if query.from_date:
            filters["from_date"] = query.from_date.isoformat()
        if query.to_date:
            filters["to_date"] = query.to_date.isoformat()
        
        return filters
    
    async def _process_export(
        self,
        export_id: str,
        export_request: AuditExportRequest,
        user_context: Dict[str, Any]
    ):
        """백그라운드 내보내기 처리"""
        try:
            # 시뮬레이션: 점진적 진행률 업데이트
            for progress in [25, 50, 75, 100]:
                await asyncio.sleep(1)  # 실제로는 더 오래 걸림
                logger.info(f"Export {export_id} progress: {progress}%")
            
            logger.info(f"Export {export_id} completed")
            
        except Exception as e:
            logger.error(f"Export {export_id} failed: {str(e)}")