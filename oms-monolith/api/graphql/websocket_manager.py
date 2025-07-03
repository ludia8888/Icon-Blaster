"""
GraphQL WebSocket Manager
GraphQL 구독을 위한 WebSocket 연결 관리
"""
import asyncio
import json
import logging
from typing import Dict, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from dataclasses import dataclass
import time

from .realtime_publisher import realtime_publisher, RealtimeEvent, EventType

logger = logging.getLogger(__name__)

@dataclass
class WebSocketConnection:
    """WebSocket 연결"""
    websocket: WebSocket
    user_id: str
    connection_id: str
    subscription_id: Optional[str] = None
    connected_at: float = None
    last_ping: float = None
    
    def __post_init__(self):
        if self.connected_at is None:
            self.connected_at = time.time()
        if self.last_ping is None:
            self.last_ping = time.time()

class WebSocketManager:
    """WebSocket 연결 관리자"""
    
    def __init__(self):
        self.connections: Dict[str, WebSocketConnection] = {}
        self.user_connections: Dict[str, Set[str]] = {}
        self._heartbeat_task = None
        # Don't start heartbeat in __init__ to avoid event loop issues
    
    def _start_heartbeat(self):
        """하트비트 작업 시작"""
        async def heartbeat():
            while True:
                try:
                    await asyncio.sleep(30)  # 30초마다 핑
                    current_time = time.time()
                    disconnected = []
                    
                    for conn_id, connection in self.connections.items():
                        try:
                            # 60초 이상 무응답 시 연결 끊기
                            if current_time - connection.last_ping > 60:
                                disconnected.append(conn_id)
                                continue
                            
                            await connection.websocket.send_text(json.dumps({
                                "type": "ping",
                                "timestamp": current_time
                            }))
                        except Exception as e:
                            logger.warning(f"Failed to ping connection {conn_id}: {e}")
                            disconnected.append(conn_id)
                    
                    for conn_id in disconnected:
                        await self.disconnect(conn_id)
                        
                except Exception as e:
                    logger.error(f"Heartbeat error: {e}")
        
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(heartbeat())
    
    async def connect(self, websocket: WebSocket, user_id: str) -> str:
        """연결 등록"""
        await websocket.accept()
        
        # Start heartbeat task on first connection if not already started
        if self._heartbeat_task is None:
            self._start_heartbeat()
        
        connection_id = f"{user_id}_{int(time.time() * 1000)}"
        connection = WebSocketConnection(
            websocket=websocket,
            user_id=user_id,
            connection_id=connection_id
        )
        
        self.connections[connection_id] = connection
        
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(connection_id)
        
        logger.info(f"WebSocket connected: {connection_id} for user {user_id}")
        
        # 연결 확인 메시지 전송
        await websocket.send_text(json.dumps({
            "type": "connection_ack",
            "connection_id": connection_id
        }))
        
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """연결 해제"""
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        user_id = connection.user_id
        
        # 구독 해제
        if connection.subscription_id:
            await realtime_publisher.unsubscribe(connection.subscription_id)
        
        # WebSocket 연결 정리
        try:
            await connection.websocket.close()
        except Exception:
            pass
        
        del self.connections[connection_id]
        
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        logger.info(f"WebSocket disconnected: {connection_id}")
    
    async def subscribe_to_events(self, connection_id: str, event_types: Set[EventType]) -> bool:
        """이벤트 구독"""
        if connection_id not in self.connections:
            return False
        
        connection = self.connections[connection_id]
        
        # 기존 구독이 있으면 해제
        if connection.subscription_id:
            await realtime_publisher.unsubscribe(connection.subscription_id)
        
        # 새 구독 생성
        subscription_id = await realtime_publisher.subscribe(
            connection.user_id, 
            event_types
        )
        connection.subscription_id = subscription_id
        
        # 이벤트 스트림 시작
        asyncio.create_task(self._stream_events(connection_id))
        
        logger.info(f"Subscribed connection {connection_id} to {event_types}")
        return True
    
    async def _stream_events(self, connection_id: str):
        """이벤트 스트림 처리"""
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        if not connection.subscription_id:
            return
        
        try:
            async for event in realtime_publisher.get_subscription_events(connection.subscription_id):
                if connection_id not in self.connections:
                    break
                
                message = {
                    "type": "event",
                    "event_type": event.event_type,
                    "payload": event.payload,
                    "timestamp": event.timestamp
                }
                
                await connection.websocket.send_text(json.dumps(message))
                
        except Exception as e:
            logger.error(f"Event streaming error for {connection_id}: {e}")
            await self.disconnect(connection_id)
    
    async def handle_message(self, connection_id: str, message: str):
        """클라이언트 메시지 처리"""
        if connection_id not in self.connections:
            return
        
        connection = self.connections[connection_id]
        
        try:
            data = json.loads(message)
            message_type = data.get("type")
            
            if message_type == "pong":
                connection.last_ping = time.time()
            
            elif message_type == "subscribe":
                event_types = set()
                for event_type_str in data.get("event_types", []):
                    try:
                        event_types.add(EventType(event_type_str))
                    except ValueError:
                        logger.warning(f"Unknown event type: {event_type_str}")
                
                success = await self.subscribe_to_events(connection_id, event_types)
                
                response = {
                    "type": "subscribe_response",
                    "success": success,
                    "subscription_id": connection.subscription_id
                }
                await connection.websocket.send_text(json.dumps(response))
            
            elif message_type == "unsubscribe":
                if connection.subscription_id:
                    await realtime_publisher.unsubscribe(connection.subscription_id)
                    connection.subscription_id = None
                
                response = {"type": "unsubscribe_response", "success": True}
                await connection.websocket.send_text(json.dumps(response))
            
        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON from {connection_id}: {message}")
        except Exception as e:
            logger.error(f"Message handling error for {connection_id}: {e}")
    
    def get_connection_count(self) -> int:
        """활성 연결 수"""
        return len(self.connections)
    
    def get_user_connection_count(self, user_id: str) -> int:
        """사용자별 연결 수"""
        return len(self.user_connections.get(user_id, set()))

# 전역 WebSocket 매니저 인스턴스
websocket_manager = WebSocketManager()

# WebSocket 엔드포인트용 헬퍼 함수
async def handle_websocket_connection(websocket: WebSocket, user_id: str):
    """WebSocket 연결 처리"""
    connection_id = await websocket_manager.connect(websocket, user_id)
    
    try:
        while True:
            message = await websocket.receive_text()
            await websocket_manager.handle_message(connection_id, message)
            
    except WebSocketDisconnect:
        await websocket_manager.disconnect(connection_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket_manager.disconnect(connection_id)