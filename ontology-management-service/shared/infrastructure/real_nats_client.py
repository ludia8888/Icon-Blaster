"""
Real NATS Client Implementation with JetStream support
"""
import asyncio
import json
import os
from typing import Callable, Optional, Dict, Any, List
from datetime import datetime
import nats
from nats.aio.client import Client as NATS
from nats.js import JetStreamContext
from nats.js.errors import NotFoundError
from nats.errors import TimeoutError, NoServersError

from common_logging.setup import get_logger

logger = get_logger(__name__)


class RealNATSClient:
    """Production-ready NATS client with JetStream support"""
    
    def __init__(self, servers: Optional[List[str]] = None):
        self.servers = servers or [os.getenv("NATS_URL", "nats://localhost:4222")]
        self.nc: Optional[NATS] = None
        self.js: Optional[JetStreamContext] = None
        self.subscriptions = []
        
    async def connect(self, max_reconnect_attempts: int = 10):
        """Connect to NATS with retry logic"""
        if self.nc and self.nc.is_connected:
            logger.info("Already connected to NATS")
            return
            
        self.nc = NATS()
        
        async def error_cb(e):
            logger.error(f"NATS error: {e}")
            
        async def disconnected_cb():
            logger.warning("Disconnected from NATS")
            
        async def reconnected_cb():
            logger.info("Reconnected to NATS")
            
        async def closed_cb():
            logger.info("NATS connection closed")
            
        try:
            await self.nc.connect(
                servers=self.servers,
                error_cb=error_cb,
                disconnected_cb=disconnected_cb,
                reconnected_cb=reconnected_cb,
                closed_cb=closed_cb,
                max_reconnect_attempts=max_reconnect_attempts,
                reconnect_time_wait=2,
                ping_interval=10
            )
            
            # Initialize JetStream
            self.js = self.nc.jetstream()
            
            # Ensure audit stream exists
            await self._ensure_audit_stream()
            
            logger.info(f"Connected to NATS at {self.servers}")
            
        except NoServersError:
            logger.error(f"Failed to connect to NATS servers: {self.servers}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to NATS: {e}")
            raise
            
    async def _ensure_audit_stream(self):
        """Ensure the audit events stream exists"""
        stream_name = "AUDIT_EVENTS"
        
        try:
            # Check if stream exists
            await self.js.stream_info(stream_name)
            logger.info(f"Stream {stream_name} already exists")
        except NotFoundError:
            # Create stream
            await self.js.add_stream(
                name=stream_name,
                subjects=["audit.>", "events.audit.>"],
                retention="limits",
                max_msgs=1000000,  # 1M messages
                max_bytes=1024*1024*1024,  # 1GB
                max_age=86400*30,  # 30 days
                storage="file",
                num_replicas=1,
                duplicate_window=120  # 2 minute deduplication window
            )
            logger.info(f"Created stream {stream_name}")
            
    async def publish(self, subject: str, data: Any, headers: Optional[Dict[str, str]] = None):
        """Publish message to NATS"""
        if not self.nc or not self.nc.is_connected:
            raise RuntimeError("Not connected to NATS")
            
        try:
            # Convert data to bytes
            if isinstance(data, (dict, list)):
                payload = json.dumps(data).encode()
            elif isinstance(data, str):
                payload = data.encode()
            elif isinstance(data, bytes):
                payload = data
            else:
                payload = str(data).encode()
                
            # Publish with optional headers
            if headers:
                await self.nc.publish(subject, payload, headers=headers)
            else:
                await self.nc.publish(subject, payload)
                
            logger.debug(f"Published message to {subject}")
            
        except Exception as e:
            logger.error(f"Failed to publish to {subject}: {e}")
            raise
            
    async def publish_with_reply(self, subject: str, data: Any, timeout: float = 5.0) -> Any:
        """Publish and wait for reply"""
        if not self.nc or not self.nc.is_connected:
            raise RuntimeError("Not connected to NATS")
            
        try:
            # Convert data to bytes
            if isinstance(data, (dict, list)):
                payload = json.dumps(data).encode()
            else:
                payload = str(data).encode()
                
            # Request with timeout
            msg = await self.nc.request(subject, payload, timeout=timeout)
            
            # Try to decode as JSON
            try:
                return json.loads(msg.data.decode())
            except:
                return msg.data.decode()
                
        except TimeoutError:
            logger.error(f"Request to {subject} timed out")
            raise
        except Exception as e:
            logger.error(f"Failed to request {subject}: {e}")
            raise
            
    async def subscribe(self, subject: str, cb: Callable, queue: Optional[str] = None):
        """Subscribe to a subject"""
        if not self.nc or not self.nc.is_connected:
            raise RuntimeError("Not connected to NATS")
            
        async def wrapped_cb(msg):
            """Wrapper to handle message parsing"""
            try:
                # Try to parse as JSON
                try:
                    data = json.loads(msg.data.decode())
                except:
                    data = msg.data.decode()
                    
                # Call the callback with parsed data
                await cb(subject=msg.subject, data=data, reply=msg.reply)
                
            except Exception as e:
                logger.error(f"Error in subscription callback for {subject}: {e}")
                
        try:
            if queue:
                sub = await self.nc.subscribe(subject, queue=queue, cb=wrapped_cb)
            else:
                sub = await self.nc.subscribe(subject, cb=wrapped_cb)
                
            self.subscriptions.append(sub)
            logger.info(f"Subscribed to {subject}" + (f" with queue {queue}" if queue else ""))
            
            return sub
            
        except Exception as e:
            logger.error(f"Failed to subscribe to {subject}: {e}")
            raise
            
    async def jetstream_publish(self, subject: str, data: Any, 
                               msg_id: Optional[str] = None,
                               expected_stream: Optional[str] = None) -> Any:
        """Publish to JetStream with deduplication"""
        if not self.js:
            raise RuntimeError("JetStream not initialized")
            
        try:
            # Convert data to bytes
            if isinstance(data, (dict, list)):
                payload = json.dumps(data).encode()
            else:
                payload = str(data).encode()
                
            # Publish with optional message ID for deduplication
            headers = {}
            if msg_id:
                headers["Nats-Msg-Id"] = msg_id
            if expected_stream:
                headers["Nats-Expected-Stream"] = expected_stream
                
            ack = await self.js.publish(subject, payload, headers=headers if headers else None)
            
            logger.debug(f"Published to JetStream {subject}: seq={ack.seq}, stream={ack.stream}")
            
            return {
                "seq": ack.seq,
                "stream": ack.stream,
                "duplicate": ack.duplicate
            }
            
        except Exception as e:
            logger.error(f"Failed to publish to JetStream {subject}: {e}")
            raise
            
    async def jetstream_subscribe(self, subject: str, durable: str, 
                                 cb: Callable, 
                                 manual_ack: bool = True,
                                 ack_wait: int = 30):
        """Subscribe via JetStream with durable consumer"""
        if not self.js:
            raise RuntimeError("JetStream not initialized")
            
        async def wrapped_cb(msg):
            """Wrapper to handle JetStream messages"""
            try:
                # Parse message
                try:
                    data = json.loads(msg.data.decode())
                except:
                    data = msg.data.decode()
                    
                # Call the callback
                result = await cb(
                    subject=msg.subject,
                    data=data,
                    msg_id=msg.headers.get("Nats-Msg-Id") if msg.headers else None,
                    seq=msg.metadata.sequence,
                    timestamp=msg.metadata.timestamp
                )
                
                # Auto-ack if successful and manual_ack is False
                if not manual_ack and result is not False:
                    await msg.ack()
                    
            except Exception as e:
                logger.error(f"Error in JetStream callback for {subject}: {e}")
                if not manual_ack:
                    await msg.nak()  # Negative acknowledgment
                    
        try:
            # Create pull subscription
            sub = await self.js.pull_subscribe(
                subject,
                durable=durable,
                config={
                    "ack_wait": ack_wait,
                    "max_deliver": 3,
                    "filter_subject": subject
                }
            )
            
            # Start consuming messages
            asyncio.create_task(self._consume_messages(sub, wrapped_cb))
            
            self.subscriptions.append(sub)
            logger.info(f"JetStream subscription created: {subject} (durable: {durable})")
            
            return sub
            
        except Exception as e:
            logger.error(f"Failed to create JetStream subscription: {e}")
            raise
            
    async def _consume_messages(self, subscription, cb: Callable):
        """Consume messages from pull subscription"""
        try:
            while True:
                try:
                    # Fetch messages with timeout
                    messages = await subscription.fetch(batch=10, timeout=1)
                    
                    for msg in messages:
                        await cb(msg)
                        
                except TimeoutError:
                    # Normal timeout, continue
                    continue
                except Exception as e:
                    logger.error(f"Error consuming messages: {e}")
                    await asyncio.sleep(5)  # Back off on error
                    
        except asyncio.CancelledError:
            logger.info("Message consumer cancelled")
            
    async def close(self):
        """Close NATS connection"""
        try:
            # Unsubscribe from all subscriptions
            for sub in self.subscriptions:
                try:
                    await sub.unsubscribe()
                except:
                    pass
                    
            self.subscriptions.clear()
            
            # Close connection
            if self.nc:
                await self.nc.close()
                
            logger.info("NATS connection closed")
            
        except Exception as e:
            logger.error(f"Error closing NATS connection: {e}")
            
    async def health_check(self) -> Dict[str, Any]:
        """Check NATS connection health"""
        if not self.nc:
            return {
                "status": "disconnected",
                "connected": False,
                "servers": self.servers
            }
            
        return {
            "status": "connected" if self.nc.is_connected else "disconnected",
            "connected": self.nc.is_connected,
            "servers": self.servers,
            "stats": {
                "in_msgs": self.nc.stats["in_msgs"],
                "out_msgs": self.nc.stats["out_msgs"],
                "in_bytes": self.nc.stats["in_bytes"],
                "out_bytes": self.nc.stats["out_bytes"],
                "reconnects": self.nc.stats["reconnects"]
            }
        }


# Singleton instance
_nats_client: Optional[RealNATSClient] = None


async def get_nats_client() -> RealNATSClient:
    """Get or create NATS client instance"""
    global _nats_client
    
    if not _nats_client:
        _nats_client = RealNATSClient()
        await _nats_client.connect()
        
    return _nats_client


# Compatibility function for existing code
async def get_real_nats_client() -> RealNATSClient:
    """Alias for get_nats_client"""
    return await get_nats_client()