"""
Base message store interface for DLQ
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from datetime import datetime
from ..models import DLQMessage, MessageStatus


class MessageStore(ABC):
    """Abstract base class for DLQ message storage"""
    
    @abstractmethod
    async def store(self, message: DLQMessage) -> bool:
        """Store a message in the DLQ"""
        pass
    
    @abstractmethod
    async def get(self, queue_name: str, message_id: str) -> Optional[DLQMessage]:
        """Get a specific message"""
        pass
    
    @abstractmethod
    async def list_messages(
        self,
        queue_name: str,
        status: Optional[MessageStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[DLQMessage]:
        """List messages in queue with optional filtering"""
        pass
    
    @abstractmethod
    async def update(self, message: DLQMessage) -> bool:
        """Update an existing message"""
        pass
    
    @abstractmethod
    async def delete(self, queue_name: str, message_id: str) -> bool:
        """Delete a message from the DLQ"""
        pass
    
    @abstractmethod
    async def get_ready_for_retry(
        self,
        queue_name: str,
        limit: int = 10
    ) -> List[DLQMessage]:
        """Get messages ready for retry"""
        pass
    
    @abstractmethod
    async def get_expired(
        self,
        queue_name: str,
        limit: int = 100
    ) -> List[DLQMessage]:
        """Get expired messages"""
        pass
    
    @abstractmethod
    async def count_by_status(
        self,
        queue_name: str
    ) -> Dict[MessageStatus, int]:
        """Count messages by status"""
        pass
    
    @abstractmethod
    async def cleanup_old_messages(
        self,
        queue_name: str,
        older_than: datetime
    ) -> int:
        """Clean up old messages, return count deleted"""
        pass