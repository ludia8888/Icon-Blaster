"""
Audit Service Provider
DI 컨테이너용 audit service provider
"""
import os
from typing import Optional
from .base import Provider
from shared.audit_client import AuditServiceClient
from core.audit.audit_service import AuditService


class AuditServiceProvider(Provider[AuditService]):
    """Audit Service Provider for DI Container"""
    
    def __init__(self):
        self.use_audit_service = os.getenv('USE_AUDIT_SERVICE', 'false').lower() == 'true'
        self._audit_service: Optional[AuditService] = None
    
    def get(self) -> AuditService:
        """Get audit service instance"""
        if self._audit_service is None:
            self._audit_service = AuditService()
        return self._audit_service
    
    async def initialize(self):
        """Initialize audit service"""
        service = self.get()
        await service.initialize()
    
    async def cleanup(self):
        """Cleanup audit service"""
        if self._audit_service:
            await self._audit_service.close()
            self._audit_service = None


class AuditClientProvider(Provider[AuditServiceClient]):
    """Direct Audit Client Provider (bypasses adapter)"""
    
    def __init__(self):
        self._client: Optional[AuditServiceClient] = None
    
    def get(self) -> AuditServiceClient:
        """Get audit client instance"""
        if self._client is None:
            self._client = AuditServiceClient()
        return self._client
    
    async def cleanup(self):
        """Cleanup audit client"""
        if self._client:
            await self._client.close()
            self._client = None