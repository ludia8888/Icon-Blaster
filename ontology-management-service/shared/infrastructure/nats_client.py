"""
NATS Client Module
Exports the real NATS client implementation when available
"""
import os

# Check if we should use the real implementation
USE_REAL_NATS = os.getenv("ENABLE_REAL_NATS", "true").lower() == "true"

if USE_REAL_NATS:
    try:
        # Try to import real implementation
        from .real_nats_client import RealNATSClient as NATSClient, get_nats_client, get_real_nats_client
        print("✅ Using real NATS client implementation")
    except ImportError:
        # Fall back to dummy if real client dependencies not available
        print("⚠️  Real NATS client not available, using dummy implementation")
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
        
        async def get_nats_client():
            """Get dummy NATS client"""
            client = NATSClient()
            await client.connect()
            return client
            
        get_real_nats_client = get_nats_client
else:
    # Explicitly use dummy implementation
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
    
    async def get_nats_client():
        """Get dummy NATS client"""
        client = NATSClient()
        await client.connect()
        return client
        
    get_real_nats_client = get_nats_client

__all__ = ['NATSClient', 'get_nats_client', 'get_real_nats_client']