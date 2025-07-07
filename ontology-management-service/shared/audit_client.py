"""
Audit Service Client
OMS 모놀리스에서 audit-service로의 HTTP 클라이언트
"""
import os
import asyncio
import uuid
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, asdict
import httpx
import json
from contextlib import asynccontextmanager

# from shared.grpc_interceptors import RetryConfig, CircuitBreakerConfig

@dataclass 
class RetryConfig:
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0

@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 60.0


@dataclass
class AuditEvent:
    """감사 이벤트 데이터 클래스"""
    event_type: str
    event_category: str
    user_id: str
    username: str
    target_type: str
    target_id: str
    operation: str
    severity: str = "INFO"
    service_account: Optional[str] = None
    branch: Optional[str] = None
    commit_id: Optional[str] = None
    terminus_db: Optional[str] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    before_state: Optional[Dict[str, Any]] = None
    after_state: Optional[Dict[str, Any]] = None
    changes: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        data = asdict(self)
        if self.timestamp:
            data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class AuditEventBatch:
    """감사 이벤트 배치"""
    events: List[AuditEvent]
    batch_id: Optional[str] = None
    source_service: str = "oms-monolith"
    
    def __post_init__(self):
        if self.batch_id is None:
            self.batch_id = str(uuid.uuid4())
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "events": [event.to_dict() for event in self.events],
            "batch_id": self.batch_id,
            "source_service": self.source_service
        }


class AuditServiceClient:
    """Audit Service HTTP 클라이언트"""
    
    def __init__(self):
        self.base_url = os.getenv('AUDIT_SERVICE_URL', 'http://audit-service:8004')
        self.api_key = os.getenv('AUDIT_SERVICE_API_KEY', '')
        self.timeout = float(os.getenv('AUDIT_SERVICE_TIMEOUT', '30.0'))
        self.max_retries = int(os.getenv('AUDIT_SERVICE_MAX_RETRIES', '3'))
        self.circuit_breaker_threshold = int(os.getenv('AUDIT_SERVICE_CB_THRESHOLD', '5'))
        
        # HTTP 클라이언트 설정
        self._client: Optional[httpx.AsyncClient] = None
        self._circuit_breaker_failures = 0
        self._circuit_breaker_last_failure = None
        self._circuit_breaker_open = False
        
        # 백그라운드 큐 (옵션)
        self._background_queue: Optional[asyncio.Queue] = None
        self._background_task: Optional[asyncio.Task] = None
        
    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 가져오기 (지연 초기화)"""
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "oms-monolith/audit-client"
            }
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=5)
            )
        return self._client
    
    async def close(self):
        """클라이언트 종료"""
        if self._client:
            await self._client.aclose()
            self._client = None
        
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
    
    def _check_circuit_breaker(self):
        """Circuit Breaker 상태 확인"""
        if not self._circuit_breaker_open:
            return True
        
        # 30초 후 하프-오픈 상태로 전환
        if (self._circuit_breaker_last_failure and 
            (datetime.utcnow() - self._circuit_breaker_last_failure).seconds > 30):
            self._circuit_breaker_open = False
            self._circuit_breaker_failures = 0
            return True
        
        return False
    
    def _record_failure(self):
        """실패 기록 및 Circuit Breaker 업데이트"""
        self._circuit_breaker_failures += 1
        self._circuit_breaker_last_failure = datetime.utcnow()
        
        if self._circuit_breaker_failures >= self.circuit_breaker_threshold:
            self._circuit_breaker_open = True
    
    def _record_success(self):
        """성공 기록 및 Circuit Breaker 리셋"""
        self._circuit_breaker_failures = 0
        self._circuit_breaker_open = False
        self._circuit_breaker_last_failure = None
    
    async def record_event(self, event: AuditEvent) -> str:
        """단일 감사 이벤트 기록"""
        if not self._check_circuit_breaker():
            raise Exception("Audit service circuit breaker is open")
        
        client = await self._get_client()
        
        for attempt in range(self.max_retries):
            try:
                response = await client.post(
                    "/api/v2/events/single",
                    json=event.to_dict()
                )
                response.raise_for_status()
                result = response.json()
                
                self._record_success()
                return result.get("event_id", "unknown")
                
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt == self.max_retries - 1:
                    self._record_failure()
                    raise Exception(f"Failed to record audit event after {self.max_retries} attempts: {e}")
                
                # 지수 백오프
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
    
    async def record_events_batch(self, batch: AuditEventBatch) -> Dict[str, Any]:
        """배치 감사 이벤트 기록"""
        if not self._check_circuit_breaker():
            raise Exception("Audit service circuit breaker is open")
        
        client = await self._get_client()
        
        for attempt in range(self.max_retries):
            try:
                response = await client.post(
                    "/api/v2/events/batch",
                    json=batch.to_dict()
                )
                response.raise_for_status()
                result = response.json()
                
                self._record_success()
                return result
                
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                if attempt == self.max_retries - 1:
                    self._record_failure()
                    raise Exception(f"Failed to record audit batch after {self.max_retries} attempts: {e}")
                
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
    
    async def query_events(
        self,
        user_id: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[str] = None,
        operation: Optional[str] = None,
        branch: Optional[str] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """감사 이벤트 조회"""
        if not self._check_circuit_breaker():
            raise Exception("Audit service circuit breaker is open")
        
        client = await self._get_client()
        
        params = {
            "limit": limit,
            "offset": offset
        }
        
        if user_id:
            params["user_id"] = user_id
        if target_type:
            params["target_type"] = target_type
        if target_id:
            params["target_id"] = target_id
        if operation:
            params["operation"] = operation
        if branch:
            params["branch"] = branch
        if from_date:
            params["from_date"] = from_date.isoformat()
        if to_date:
            params["to_date"] = to_date.isoformat()
        
        try:
            response = await client.get("/api/v2/events/query", params=params)
            response.raise_for_status()
            
            self._record_success()
            return response.json()
            
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            self._record_failure()
            raise Exception(f"Failed to query audit events: {e}")
    
    async def health_check(self) -> bool:
        """Audit Service 헬스 체크"""
        try:
            client = await self._get_client()
            response = await client.get("/api/v2/events/health")
            return response.status_code == 200
        except:
            return False
    
    # 백그라운드 처리 메서드들
    async def record_event_async(self, event: AuditEvent):
        """비동기 백그라운드로 이벤트 기록"""
        if self._background_queue is None:
            self._background_queue = asyncio.Queue(maxsize=1000)
            self._background_task = asyncio.create_task(self._background_processor())
        
        try:
            self._background_queue.put_nowait(event)
        except asyncio.QueueFull:
            # 큐가 가득 찬 경우 동기적으로 처리
            await self.record_event(event)
    
    async def _background_processor(self):
        """백그라운드 이벤트 처리기"""
        batch_events = []
        batch_timeout = 5.0  # 5초마다 배치 전송
        
        while True:
            try:
                # 타임아웃으로 이벤트 수집
                try:
                    event = await asyncio.wait_for(
                        self._background_queue.get(),
                        timeout=batch_timeout
                    )
                    batch_events.append(event)
                except asyncio.TimeoutError:
                    pass
                
                # 배치 크기 도달하거나 타임아웃 시 전송
                if len(batch_events) >= 10 or (batch_events and len(batch_events) > 0):
                    if batch_events:
                        batch = AuditEventBatch(events=batch_events)
                        try:
                            await self.record_events_batch(batch)
                        except Exception as e:
                            # 백그라운드 처리 실패는 로깅만
                            print(f"Background audit processing failed: {e}")
                        
                        batch_events = []
                
            except asyncio.CancelledError:
                # 종료 시 남은 이벤트 처리
                if batch_events:
                    batch = AuditEventBatch(events=batch_events)
                    try:
                        await self.record_events_batch(batch)
                    except:
                        pass
                break
            except Exception as e:
                print(f"Background processor error: {e}")
                await asyncio.sleep(1)


# 전역 클라이언트 인스턴스 (선택사항)
_global_client: Optional[AuditServiceClient] = None


async def get_audit_client() -> AuditServiceClient:
    """전역 audit 클라이언트 가져오기"""
    global _global_client
    if _global_client is None:
        _global_client = AuditServiceClient()
    return _global_client


async def close_audit_client():
    """전역 audit 클라이언트 종료"""
    global _global_client
    if _global_client:
        await _global_client.close()
        _global_client = None


@asynccontextmanager
async def audit_client():
    """Context manager로 audit 클라이언트 사용"""
    client = AuditServiceClient()
    try:
        yield client
    finally:
        await client.close()