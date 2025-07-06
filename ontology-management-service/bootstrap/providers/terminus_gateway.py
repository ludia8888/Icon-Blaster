"""
TerminusDB Gateway Provider - Provides either direct or gateway access to TerminusDB
"""
import os
import logging
from typing import Union

from bootstrap.providers.base import SingletonProvider
from database.clients.terminus_db import TerminusDBClient
from shared.data_kernel_client import TerminusGatewayClient

logger = logging.getLogger(__name__)


class TerminusGatewayProvider(SingletonProvider):
    """
    Provider that returns either direct TerminusDBClient or gateway client
    based on environment configuration.
    """
    
    def __init__(self):
        super().__init__()
        self._client: Union[TerminusDBClient, TerminusGatewayClient, None] = None
        self._use_gateway = os.getenv("USE_DATA_KERNEL_GATEWAY", "false").lower() == "true"
    
    async def initialize(self):
        """Initialize the appropriate client based on configuration."""
        if self._client is None:
            if self._use_gateway:
                logger.info("Initializing TerminusDB Gateway Client (gRPC)")
                self._client = TerminusGatewayClient(
                    endpoint=os.getenv("DATA_KERNEL_GRPC_ENDPOINT", "data-kernel:50051"),
                    service_name=os.getenv("SERVICE_NAME", "oms-service")
                )
            else:
                logger.info("Initializing Direct TerminusDB Client (HTTP)")
                self._client = TerminusDBClient(
                    endpoint=os.getenv("TERMINUSDB_ENDPOINT", "http://localhost:6363"),
                    username=os.getenv("TERMINUSDB_USER", "admin"),
                    password=os.getenv("TERMINUSDB_PASS", "changeme-admin-pass"),
                    service_name=os.getenv("SERVICE_NAME", "oms-service"),
                    use_connection_pool=True
                )
            
            # Initialize the client
            await self._client.__aenter__()
            
            # Verify connectivity
            health = await self._client.ping()
            logger.info(f"TerminusDB client initialized successfully: {health}")
    
    async def get_client(self) -> Union[TerminusDBClient, TerminusGatewayClient]:
        """Get the initialized client."""
        if self._client is None:
            await self.initialize()
        return self._client
    
    async def close(self):
        """Close the client connection."""
        if self._client:
            await self._client.__aexit__(None, None, None)
            self._client = None
    
    @property
    def is_using_gateway(self) -> bool:
        """Check if using gateway mode."""
        return self._use_gateway
    
    def get_mode(self) -> str:
        """Get current connection mode."""
        return "gateway" if self._use_gateway else "direct"


# Global instance
_provider_instance: TerminusGatewayProvider = None


def get_terminus_provider() -> TerminusGatewayProvider:
    """Get or create the singleton provider instance."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = TerminusGatewayProvider()
    return _provider_instance


async def get_terminus_client() -> Union[TerminusDBClient, TerminusGatewayClient]:
    """
    Dependency injection function for FastAPI.
    Returns the appropriate TerminusDB client based on configuration.
    """
    provider = get_terminus_provider()
    return await provider.get_client()