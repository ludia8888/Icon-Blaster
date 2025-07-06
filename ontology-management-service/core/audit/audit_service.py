"""
Audit Service - Read-Only Adapter
감사 서비스를 audit-service로 이관한 후의 read-only adapter
"""
import os
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass

# 기존 호환성을 위한 imports
from shared.audit_client import AuditServiceClient, AuditEvent, AuditEventBatch


class AuditService:
    """
    Audit Service Read-Only Adapter
    
    기존 모놀리스 코드와의 호환성을 위한 adapter 클래스
    실제 구현은 audit-service로 위임
    """
    
    def __init__(self):
        self.use_audit_service = os.getenv('USE_AUDIT_SERVICE', 'true').lower() == 'true'
        self._client: Optional[AuditServiceClient] = None
        
        # 레거시 지원을 위한 내부 상태
        self._initialized = False
        self._deprecation_warned = False
    
    async def _get_client(self) -> AuditServiceClient:
        """Audit Service 클라이언트 가져오기"""
        if self._client is None:
            self._client = AuditServiceClient()
        return self._client
    
    def _warn_deprecation(self, method_name: str):
        """Deprecation 경고 출력 (한 번만)"""
        if not self._deprecation_warned:
            print(f"⚠️  DEPRECATION WARNING: {method_name} in core.audit.audit_service is deprecated. "
                  f"Use shared.audit_client.AuditServiceClient directly.")
            self._deprecation_warned = True
    
    async def initialize(self):
        """서비스 초기화"""
        if self._initialized:
            return
        
        if self.use_audit_service:
            self._client = AuditServiceClient()
            # 연결 테스트
            try:
                health = await self._client.health_check()
                if not health:
                    print("⚠️  Warning: Audit service health check failed")
            except Exception as e:
                print(f"⚠️  Warning: Cannot connect to audit service: {e}")
        
        self._initialized = True
    
    async def close(self):
        """서비스 종료"""
        if self._client:
            await self._client.close()
            self._client = None
        self._initialized = False
    
    # =============================================================================
    # 메인 감사 이벤트 기록 메서드 (audit-service로 위임)
    # =============================================================================
    
    async def record_event(
        self,
        event_type: str,
        event_category: str,
        user_id: str,
        username: str,
        target_type: str,
        target_id: str,
        operation: str,
        severity: str = "INFO",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        감사 이벤트 기록 (audit-service로 위임)
        
        Args:
            event_type: 이벤트 타입
            event_category: 이벤트 카테고리
            user_id: 사용자 ID
            username: 사용자명
            target_type: 대상 타입
            target_id: 대상 ID
            operation: 수행된 작업
            severity: 심각도
            metadata: 추가 메타데이터
            **kwargs: 추가 필드들
        
        Returns:
            str: 이벤트 ID
        """
        self._warn_deprecation("record_event")
        
        if not self.use_audit_service:
            # 로컬 모드 (테스트용)
            return f"local_event_{datetime.utcnow().isoformat()}"
        
        await self.initialize()
        client = await self._get_client()
        
        # AuditEvent 객체 생성
        event = AuditEvent(
            event_type=event_type,
            event_category=event_category,
            user_id=user_id,
            username=username,
            target_type=target_type,
            target_id=target_id,
            operation=operation,
            severity=severity,
            metadata=metadata,
            # kwargs에서 추가 필드 추출
            service_account=kwargs.get('service_account'),
            branch=kwargs.get('branch'),
            commit_id=kwargs.get('commit_id'),
            terminus_db=kwargs.get('terminus_db'),
            request_id=kwargs.get('request_id'),
            session_id=kwargs.get('session_id'),
            ip_address=kwargs.get('ip_address'),
            user_agent=kwargs.get('user_agent'),
            before_state=kwargs.get('before_state'),
            after_state=kwargs.get('after_state'),
            changes=kwargs.get('changes')
        )
        
        return await client.record_event(event)
    
    async def query_events(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs
    ) -> Dict[str, Any]:
        """
        감사 이벤트 조회
        
        Args:
            filters: 필터 조건
            limit: 결과 제한
            offset: 오프셋
            **kwargs: 추가 필터 조건
        
        Returns:
            Dict: 조회 결과
        """
        self._warn_deprecation("query_events")
        
        if not self.use_audit_service:
            return {
                "success": True,
                "total": 0,
                "events": [],
                "limit": limit,
                "offset": offset
            }
        
        await self.initialize()
        client = await self._get_client()
        
        # 필터 조건 변환
        user_id = None
        target_type = None
        target_id = None
        operation = None
        branch = None
        from_date = None
        to_date = None
        
        if filters:
            user_id = filters.get('user_id')
            target_type = filters.get('target_type')
            target_id = filters.get('target_id')
            operation = filters.get('operation')
            branch = filters.get('metadata.branch')
            if 'timestamp__gte' in filters:
                from_date = filters['timestamp__gte']
            if 'timestamp__lte' in filters:
                to_date = filters['timestamp__lte']
        
        # kwargs에서 추가 필터 추출
        user_id = user_id or kwargs.get('user_id')
        target_type = target_type or kwargs.get('target_type')
        target_id = target_id or kwargs.get('target_id')
        operation = operation or kwargs.get('operation')
        branch = branch or kwargs.get('branch')
        from_date = from_date or kwargs.get('from_date')
        to_date = to_date or kwargs.get('to_date')
        
        return await client.query_events(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            operation=operation,
            branch=branch,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset
        )
    
    async def health_check(self) -> bool:
        """서비스 상태 확인"""
        if not self.use_audit_service:
            return True
        
        try:
            client = await self._get_client()
            return await client.health_check()
        except Exception:
            return False


# =============================================================================
# 백워드 호환성을 위한 레거시 함수들
# =============================================================================

_global_audit_service: Optional[AuditService] = None


async def get_audit_service() -> AuditService:
    """전역 audit service 인스턴스 가져오기"""
    global _global_audit_service
    if _global_audit_service is None:
        _global_audit_service = AuditService()
        await _global_audit_service.initialize()
    return _global_audit_service