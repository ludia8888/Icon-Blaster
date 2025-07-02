"""HTTP backend for event publishing"""

import logging
from typing import Dict, Any, List, Optional
import httpx

from core.events.unified_publisher import EventPublisherBackend, PublisherConfig
from database.clients.unified_http_client import UnifiedHTTPClient, create_basic_client, HTTPClientConfig

logger = logging.getLogger(__name__)


class HTTPEventBackend(EventPublisherBackend):
    """HTTP-based event publishing backend"""
    
    def __init__(self, config: PublisherConfig):
        self.config = config
        self.endpoint = config.endpoint or "http://localhost:8000"
        self.client: Optional[UnifiedHTTPClient] = None
    
    async def connect(self) -> None:
        """Create HTTP client"""
        headers = {}
        if self.config.api_key:
            headers["X-API-Key"] = self.config.api_key
        
        http_config = HTTPClientConfig(
            base_url=self.endpoint,
            timeout=self.config.timeout,
            headers=headers
        )
        self.client = UnifiedHTTPClient(http_config)
        logger.info(f"Connected to HTTP endpoint: {self.endpoint}")
    
    async def disconnect(self) -> None:
        """Close HTTP client"""
        if self.client:
            await self.client.close()
            self.client = None
            logger.info("Disconnected from HTTP endpoint")
    
    async def publish(self, event: Dict[str, Any]) -> bool:
        """Publish single event via HTTP"""
        if not self.client:
            logger.error("HTTP client not connected")
            return False
        
        try:
            response = await self.client.post(
                "/api/v1/events",
                json=event
            )
            
            if response.status_code in [200, 201, 202]:
                logger.debug(f"Published event: {event.get('type', 'unknown')}")
                return True
            else:
                logger.error(f"Failed to publish event: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"HTTP publish error: {e}")
            return False
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Publish multiple events via HTTP"""
        if not self.client:
            logger.error("HTTP client not connected")
            return False
        
        try:
            response = await self.client.post(
                "/api/v1/events/batch",
                json={"events": events}
            )
            
            if response.status_code in [200, 201, 202]:
                logger.debug(f"Published batch of {len(events)} events")
                return True
            else:
                logger.error(f"Failed to publish batch: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"HTTP batch publish error: {e}")
            return False
    
    async def health_check(self) -> bool:
        """Check HTTP endpoint health"""
        if not self.client:
            return False
        
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except:
            return False