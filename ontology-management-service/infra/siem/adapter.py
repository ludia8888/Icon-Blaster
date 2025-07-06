"""
SIEM Adapter 구현체들
실제 SIEM 시스템과의 통신을 담당
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
import aiohttp
from collections import deque

from .port import ISiemPort

logger = logging.getLogger(__name__)


class SiemHttpAdapter(ISiemPort):
    """HTTP 기반 SIEM 어댑터 (Splunk, ELK 등)"""
    
    def __init__(self, endpoint: str, token: str, timeout: int = 30):
        self.endpoint = endpoint
        self.token = token
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTP 세션 관리"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._session
    
    async def send(self, event_type: str, payload: Dict[str, Any]) -> None:
        """단일 이벤트 전송"""
        try:
            session = await self._get_session()
            
            # SIEM 형식으로 래핑
            siem_event = {
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": event_type,
                "source": "oms_validation",
                "data": payload
            }
            
            async with session.post(
                f"{self.endpoint}/events",
                json=siem_event
            ) as response:
                if response.status not in (200, 201, 202):
                    logger.error(f"SIEM send failed: {response.status}")
                    raise Exception(f"SIEM send failed with status {response.status}")
                    
        except Exception as e:
            logger.error(f"Failed to send event to SIEM: {e}")
            raise
    
    async def send_batch(self, events: List[Dict[str, Any]]) -> None:
        """배치 이벤트 전송"""
        try:
            session = await self._get_session()
            
            # SIEM 배치 형식으로 래핑
            batch_payload = {
                "timestamp": datetime.utcnow().isoformat(),
                "source": "oms_validation",
                "events": events
            }
            
            async with session.post(
                f"{self.endpoint}/batch",
                json=batch_payload
            ) as response:
                if response.status not in (200, 201, 202):
                    logger.error(f"SIEM batch send failed: {response.status}")
                    raise Exception(f"SIEM batch send failed with status {response.status}")
                    
        except Exception as e:
            logger.error(f"Failed to send batch to SIEM: {e}")
            raise
    
    async def query(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """SIEM 이벤트 조회"""
        try:
            session = await self._get_session()
            
            async with session.get(
                f"{self.endpoint}/search",
                params=query_params
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"SIEM query failed: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Failed to query SIEM: {e}")
            return []
    
    async def health_check(self) -> bool:
        """SIEM 연결 상태 확인"""
        try:
            session = await self._get_session()
            async with session.get(f"{self.endpoint}/health") as response:
                return response.status == 200
        except:
            return False
    
    async def close(self):
        """리소스 정리"""
        if self._session and not self._session.closed:
            await self._session.close()


class MockSiemAdapter(ISiemPort):
    """테스트용 Mock SIEM 어댑터"""
    
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.is_healthy = True
        self.send_count = 0
        self.batch_count = 0
    
    async def send(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Mock 이벤트 저장"""
        self.send_count += 1
        self.events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "data": payload
        })
        logger.debug(f"Mock SIEM: Received {event_type} event")
    
    async def send_batch(self, events: List[Dict[str, Any]]) -> None:
        """Mock 배치 이벤트 저장"""
        self.batch_count += 1
        self.events.extend(events)
        logger.debug(f"Mock SIEM: Received batch of {len(events)} events")
    
    async def query(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Mock 이벤트 조회"""
        # 간단한 필터링 로직
        results = []
        for event in self.events:
            if "event_type" in query_params:
                if event.get("event_type") == query_params["event_type"]:
                    results.append(event)
            else:
                results.append(event)
        return results
    
    async def health_check(self) -> bool:
        """Mock 헬스 체크"""
        return self.is_healthy
    
    def clear(self):
        """테스트용 - 저장된 이벤트 클리어"""
        self.events.clear()
        self.send_count = 0
        self.batch_count = 0


class KafkaSiemAdapter(ISiemPort):
    """Kafka 기반 SIEM 어댑터 (대용량 스트리밍용)"""
    
    def __init__(self, bootstrap_servers: str, topic: str):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        # 실제 구현시 aiokafka 사용
        logger.info(f"Kafka SIEM adapter initialized: {bootstrap_servers}/{topic}")
    
    async def send(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Kafka로 이벤트 전송"""
        # 실제 구현 예시:
        # producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        # await producer.start()
        # await producer.send(self.topic, value=json.dumps(payload).encode())
        # await producer.stop()
        logger.debug(f"Would send to Kafka: {event_type}")
    
    async def send_batch(self, events: List[Dict[str, Any]]) -> None:
        """Kafka로 배치 전송"""
        logger.debug(f"Would send batch to Kafka: {len(events)} events")
    
    async def query(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Kafka는 조회 미지원"""
        raise NotImplementedError("Kafka adapter does not support querying")
    
    async def health_check(self) -> bool:
        """Kafka 연결 확인"""
        # 실제 구현시 Kafka 연결 테스트
        return True


class BufferedSiemAdapter(ISiemPort):
    """버퍼링을 지원하는 SIEM 어댑터 래퍼"""
    
    def __init__(self, base_adapter: ISiemPort, buffer_size: int = 100, flush_interval: float = 5.0):
        self.base_adapter = base_adapter
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.buffer: deque = deque(maxlen=buffer_size)
        self._flush_task: Optional[asyncio.Task] = None
        self._start_flush_task()
    
    def _start_flush_task(self):
        """주기적 플러시 태스크 시작"""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = asyncio.create_task(self._periodic_flush())
    
    async def _periodic_flush(self):
        """주기적으로 버퍼 플러시"""
        while True:
            await asyncio.sleep(self.flush_interval)
            if self.buffer:
                await self._flush_buffer()
    
    async def _flush_buffer(self):
        """버퍼 내용을 배치로 전송"""
        if not self.buffer:
            return
            
        events = list(self.buffer)
        self.buffer.clear()
        
        try:
            await self.base_adapter.send_batch(events)
            logger.debug(f"Flushed {len(events)} events to SIEM")
        except Exception as e:
            logger.error(f"Failed to flush buffer: {e}")
            # 실패시 버퍼에 다시 추가 (선택적)
            self.buffer.extend(events)
    
    async def send(self, event_type: str, payload: Dict[str, Any]) -> None:
        """버퍼에 이벤트 추가"""
        event = {
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        self.buffer.append(event)
        
        # 버퍼가 가득 차면 즉시 플러시
        if len(self.buffer) >= self.buffer_size:
            await self._flush_buffer()
    
    async def send_batch(self, events: List[Dict[str, Any]]) -> None:
        """배치는 직접 전송"""
        await self.base_adapter.send_batch(events)
    
    async def query(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """조회는 base adapter로 위임"""
        return await self.base_adapter.query(query_params)
    
    async def health_check(self) -> bool:
        """헬스체크는 base adapter로 위임"""
        return await self.base_adapter.health_check()
    
    async def close(self):
        """리소스 정리"""
        # 남은 버퍼 플러시
        if self.buffer:
            await self._flush_buffer()
        
        # 플러시 태스크 취소
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            
        # Base adapter 정리
        if hasattr(self.base_adapter, 'close'):
            await self.base_adapter.close()