"""
Frontend Service - WebSocket Connection Manager
실시간 UI 업데이트 전담 서비스
"""
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

from fastapi import WebSocket

from shared.auth import User

logger = logging.getLogger(__name__)


class WebSocketConnection:
    """개별 WebSocket 연결 관리"""

    def __init__(self, websocket: WebSocket, user: Optional[User] = None):
        self.websocket = websocket
        self.user = user
        self.connection_id = str(uuid.uuid4())
        self.connected_at = datetime.utcnow()
        self.last_ping = datetime.utcnow()

        # 활성 구독 추적 (P4 Cache-First)
        self.active_subscriptions: Set[str] = set()

        # 연결 통계
        self.messages_sent = 0
        self.messages_received = 0

    async def send_message(self, message: dict):
        """메시지 전송"""
        try:
            await self.websocket.send_text(json.dumps(message))
            self.messages_sent += 1
        except Exception as e:
            logger.error(f"Failed to send message to {self.connection_id}: {e}")
            raise

    async def send_ping(self):
        """Ping 메시지 전송"""
        await self.send_message({
            "type": "ping",
            "timestamp": datetime.utcnow().isoformat()
        })

    def update_last_ping(self):
        """마지막 ping 시간 업데이트"""
        self.last_ping = datetime.utcnow()

    def is_alive(self, timeout_minutes: int = 5) -> bool:
        """연결 활성 상태 확인"""
        return datetime.utcnow() - self.last_ping < timedelta(minutes=timeout_minutes)

    def add_subscription(self, subscription_id: str):
        """구독 추가"""
        self.active_subscriptions.add(subscription_id)

    def remove_subscription(self, subscription_id: str):
        """구독 제거"""
        self.active_subscriptions.discard(subscription_id)

    def get_connection_info(self) -> dict:
        """연결 정보 반환"""
        return {
            "connection_id": self.connection_id,
            "user_id": self.user.user_id if self.user else None,
            "connected_at": self.connected_at.isoformat(),
            "last_ping": self.last_ping.isoformat(),
            "active_subscriptions": len(self.active_subscriptions),
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "is_alive": self.is_alive()
        }


class FrontendWebSocketManager:
    """
    Frontend Service WebSocket 연결 매니저
    
    실시간 UI 업데이트 전담:
    - 스키마 변경 알림
    - 브랜치 상태 업데이트
    - 실시간 대시보드
    - 사용자 알림
    """

    def __init__(self):
        # 활성 연결 관리
        self.connections: Dict[str, WebSocketConnection] = {}

        # 사용자별 연결 매핑 (P4 Cache-First)
        self.user_connections: Dict[str, Set[str]] = {}

        # 구독별 연결 매핑
        self.subscription_connections: Dict[str, Set[str]] = {}

        # 연결 통계
        self.total_connections = 0
        self.total_disconnections = 0

        # 백그라운드 작업
        self._cleanup_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None

    def start_background_tasks(self):
        """백그라운드 작업 시작"""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_dead_connections())
        if not self._ping_task:
            self._ping_task = asyncio.create_task(self._send_periodic_pings())

    def stop_background_tasks(self):
        """백그라운드 작업 중지"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None

    async def connect(self, websocket: WebSocket, user: Optional[User] = None) -> WebSocketConnection:
        """WebSocket 연결 수락 및 등록"""
        await websocket.accept()

        connection = WebSocketConnection(websocket, user)
        connection_id = connection.connection_id

        # 연결 등록
        self.connections[connection_id] = connection
        self.total_connections += 1

        # 사용자별 연결 매핑
        if user:
            if user.user_id not in self.user_connections:
                self.user_connections[user.user_id] = set()
            self.user_connections[user.user_id].add(connection_id)

        logger.info(f"Frontend WebSocket connected: {connection_id} (user: {user.user_id if user else 'anonymous'})")

        # 백그라운드 작업 시작
        self.start_background_tasks()

        return connection

    async def disconnect(self, connection_id: str):
        """WebSocket 연결 해제"""
        if connection_id not in self.connections:
            return

        connection = self.connections[connection_id]

        # 사용자별 연결 매핑에서 제거
        if connection.user and connection.user.user_id in self.user_connections:
            self.user_connections[connection.user.user_id].discard(connection_id)
            if not self.user_connections[connection.user.user_id]:
                del self.user_connections[connection.user.user_id]

        # 구독에서 제거
        for subscription_id in list(connection.active_subscriptions):
            self.remove_subscription(connection_id, subscription_id)

        # 연결 제거
        del self.connections[connection_id]
        self.total_disconnections += 1

        logger.info(f"Frontend WebSocket disconnected: {connection_id}")

    async def broadcast_schema_change(self, event: dict):
        """스키마 변경 사항을 UI에 브로드캐스트"""
        message = {
            "type": "schema_change",
            "event": event,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_subscription("schema_changes", message)
        logger.info(f"Broadcasted schema change to UI: {event.get('operation', 'unknown')}")

    async def broadcast_branch_update(self, event: dict):
        """브랜치 업데이트를 UI에 브로드캐스트"""
        message = {
            "type": "branch_update", 
            "event": event,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_subscription("branch_updates", message)
        logger.info(f"Broadcasted branch update to UI: {event.get('branch', 'unknown')}")

    async def send_user_notification(self, user_id: str, notification: dict):
        """특정 사용자에게 알림 전송"""
        message = {
            "type": "notification",
            "notification": notification,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.broadcast_to_user(user_id, message)
        logger.info(f"Sent notification to user {user_id}: {notification.get('title', 'unknown')}")

    def add_subscription(self, connection_id: str, subscription_id: str):
        """구독 추가"""
        if connection_id not in self.connections:
            return

        connection = self.connections[connection_id]
        connection.add_subscription(subscription_id)

        # 구독별 연결 매핑
        if subscription_id not in self.subscription_connections:
            self.subscription_connections[subscription_id] = set()
        self.subscription_connections[subscription_id].add(connection_id)

    def remove_subscription(self, connection_id: str, subscription_id: str):
        """구독 제거"""
        if connection_id in self.connections:
            connection = self.connections[connection_id]
            connection.remove_subscription(subscription_id)

        # 구독별 연결 매핑에서 제거
        if subscription_id in self.subscription_connections:
            self.subscription_connections[subscription_id].discard(connection_id)
            if not self.subscription_connections[subscription_id]:
                del self.subscription_connections[subscription_id]

    def get_subscription_connections(self, subscription_id: str) -> Set[WebSocketConnection]:
        """구독의 모든 연결 조회"""
        if subscription_id not in self.subscription_connections:
            return set()

        return {
            self.connections[conn_id]
            for conn_id in self.subscription_connections[subscription_id]
            if conn_id in self.connections
        }

    async def broadcast_to_subscription(self, subscription_id: str, message: dict):
        """구독의 모든 연결에 메시지 브로드캐스트"""
        connections = self.get_subscription_connections(subscription_id)

        if not connections:
            return

        # 병렬로 메시지 전송
        tasks = [
            connection.send_message(message)
            for connection in connections
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 실패한 연결 정리
        failed_connections = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                connection = list(connections)[i]
                failed_connections.append(connection.connection_id)
                logger.warning(f"Failed to send message to {connection.connection_id}: {result}")

        # 실패한 연결 해제
        for connection_id in failed_connections:
            await self.disconnect(connection_id)

    def get_user_connections(self, user_id: str) -> Set[WebSocketConnection]:
        """특정 사용자의 모든 연결 조회"""
        if user_id not in self.user_connections:
            return set()

        return {
            self.connections[conn_id]
            for conn_id in self.user_connections[user_id]
            if conn_id in self.connections
        }

    async def broadcast_to_user(self, user_id: str, message: dict):
        """특정 사용자의 모든 연결에 메시지 브로드캐스트"""
        connections = self.get_user_connections(user_id)

        if not connections:
            return

        tasks = [
            connection.send_message(message)
            for connection in connections
        ]

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _cleanup_dead_connections(self):
        """죽은 연결 정리 (백그라운드 작업)"""
        while True:
            try:
                dead_connections = []

                for connection_id, connection in self.connections.items():
                    if not connection.is_alive():
                        dead_connections.append(connection_id)

                # 죽은 연결 해제
                for connection_id in dead_connections:
                    await self.disconnect(connection_id)

                if dead_connections:
                    logger.info(f"Cleaned up {len(dead_connections)} dead connections")

                # 5분마다 정리
                await asyncio.sleep(300)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in connection cleanup: {e}")
                await asyncio.sleep(60)

    async def _send_periodic_pings(self):
        """주기적 ping 전송 (백그라운드 작업)"""
        while True:
            try:
                # 모든 연결에 ping 전송
                tasks = [
                    connection.send_ping()
                    for connection in self.connections.values()
                ]

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

                # 30초마다 ping 전송
                await asyncio.sleep(30)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic ping: {e}")
                await asyncio.sleep(60)

    def get_statistics(self) -> dict:
        """연결 통계 반환"""
        active_connections = len(self.connections)
        active_users = len(self.user_connections)
        active_subscriptions = len(self.subscription_connections)

        return {
            "active_connections": active_connections,
            "active_users": active_users,
            "active_subscriptions": active_subscriptions,
            "total_connections": self.total_connections,
            "total_disconnections": self.total_disconnections,
            "connection_details": [
                conn.get_connection_info()
                for conn in self.connections.values()
            ]
        }


# Global Frontend WebSocket manager instance
frontend_websocket_manager = FrontendWebSocketManager()