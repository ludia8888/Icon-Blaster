"""
NATS 클라이언트 더미 구현
"""
import asyncio
from typing import Callable, Optional

class NATSClient:
    """NATS 클라이언트 더미"""
    
    def __init__(self, servers: list = None):
        self.servers = servers or ["nats://localhost:4222"]
        self.connected = False
    
    async def connect(self):
        """연결 (더미)"""
        self.connected = True
    
    async def publish(self, subject: str, data: bytes):
        """메시지 발행 (더미)"""
        if not self.connected:
            raise RuntimeError("Not connected")
        # 실제로는 아무것도 하지 않음
    
    async def subscribe(self, subject: str, cb: Callable):
        """구독 (더미)"""
        if not self.connected:
            raise RuntimeError("Not connected")
        # 실제로는 아무것도 하지 않음
    
    async def close(self):
        """연결 종료"""
        self.connected = False