"""
Event publisher provider.
Uses event gateway stub to support both local and microservice modes.
"""

import os
from shared.event_gateway_stub import get_event_gateway_stub, EventGatewayStub
from .base import Provider
from common_logging.setup import get_logger

logger = get_logger(__name__)


class EventProvider(Provider[EventGatewayStub]):
    """Provider for event gateway service stub."""
    
    def __init__(self):
        super().__init__()
        self._stub = None
    
    async def provide(self) -> EventGatewayStub:
        """Provide event gateway stub instance."""
        if not self._stub:
            self._stub = get_event_gateway_stub()
            mode = "microservice" if os.getenv("USE_EVENT_GATEWAY", "false").lower() == "true" else "local"
            logger.info(f"Event gateway provider initialized in {mode} mode")
        return self._stub
    
    async def initialize(self) -> None:
        """Initialize the provider."""
        # Stub is initialized on first use
        pass
    
    async def shutdown(self) -> None:
        """Close event service connections."""
        # Stub cleanup is handled internally
        logger.info("Event provider shutdown complete")


# For backward compatibility
def get_event_provider() -> EventProvider:
    """Get event provider instance."""
    return EventProvider()