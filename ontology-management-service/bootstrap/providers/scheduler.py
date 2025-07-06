"""
Scheduler service provider.
Uses scheduler stub to support both local and microservice modes.
"""

import os
from shared.scheduler_stub import get_scheduler_stub, SchedulerServiceStub
from .base import Provider
from common_logging.setup import get_logger

logger = get_logger(__name__)


class SchedulerProvider(Provider[SchedulerServiceStub]):
    """Provider for scheduler service stub."""
    
    def __init__(self):
        super().__init__()
        self._stub = None
    
    async def provide(self) -> SchedulerServiceStub:
        """Provide scheduler service stub instance."""
        if not self._stub:
            self._stub = get_scheduler_stub()
            mode = "microservice" if os.getenv("USE_SCHEDULER_MS", "false").lower() == "true" else "local"
            logger.info(f"Scheduler provider initialized in {mode} mode")
        return self._stub
    
    async def initialize(self) -> None:
        """Initialize the provider."""
        # Stub is initialized on first use
        pass
    
    async def shutdown(self) -> None:
        """Clean up scheduler resources."""
        # Stub cleanup is handled internally
        logger.info("Scheduler provider shutdown complete")


# For backward compatibility
def get_scheduler_provider() -> SchedulerProvider:
    """Get scheduler provider instance."""
    return SchedulerProvider()