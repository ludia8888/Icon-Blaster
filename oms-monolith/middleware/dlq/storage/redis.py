"""
Redis-based message store for DLQ
"""
import json
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from .base import MessageStore
from ..models import DLQMessage, MessageStatus
from ...common.redis_utils import RedisClient, RedisKeyPatterns

logger = logging.getLogger(__name__)


class RedisMessageStore(MessageStore):
    """Redis implementation of DLQ message store"""
    
    def __init__(self, ttl_days: int = 7):
        self.ttl_days = ttl_days
        self.logger = logger
    
    async def store(self, message: DLQMessage) -> bool:
        """Store a message in the DLQ"""
        try:
            async with RedisClient() as client:
                # Store message data
                message_key = self._get_message_key(
                    message.queue_name, 
                    message.id
                )
                
                success = await client.set_json(
                    message_key,
                    message.to_dict(),
                    expire=timedelta(days=self.ttl_days)
                )
                
                if success:
                    # Add to queue sorted set (score = timestamp)
                    queue_key = RedisKeyPatterns.DLQ_MESSAGES.format(
                        queue_name=message.queue_name
                    )
                    
                    score = message.created_at.timestamp()
                    await client.add_to_sorted_set(
                        queue_key,
                        message.id,
                        score
                    )
                    
                    # Add to status index
                    await self._update_status_index(
                        client,
                        message.queue_name,
                        message.id,
                        message.status
                    )
                    
                    # Add to retry index if applicable
                    if message.next_retry_at:
                        await self._update_retry_index(
                            client,
                            message.queue_name,
                            message.id,
                            message.next_retry_at
                        )
                
                return success
                
        except Exception as e:
            self.logger.error(f"Failed to store message: {e}")
            return False
    
    async def get(
        self, 
        queue_name: str, 
        message_id: str
    ) -> Optional[DLQMessage]:
        """Get a specific message"""
        try:
            async with RedisClient() as client:
                message_key = self._get_message_key(queue_name, message_id)
                data = await client.get_json(message_key)
                
                if data:
                    return DLQMessage.from_dict(data)
                
                return None
                
        except Exception as e:
            self.logger.error(f"Failed to get message: {e}")
            return None
    
    async def list_messages(
        self,
        queue_name: str,
        status: Optional[MessageStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[DLQMessage]:
        """List messages in queue with optional filtering"""
        try:
            async with RedisClient() as client:
                if status:
                    # Get from status index
                    status_key = self._get_status_key(queue_name, status)
                    message_ids = await client.client.smembers(status_key)
                    message_ids = list(message_ids)[offset:offset+limit]
                else:
                    # Get from main queue
                    queue_key = RedisKeyPatterns.DLQ_MESSAGES.format(
                        queue_name=queue_name
                    )
                    message_ids = await client.get_sorted_set_range(
                        queue_key,
                        offset,
                        offset + limit - 1
                    )
                
                # Fetch messages
                messages = []
                for message_id in message_ids:
                    message = await self.get(queue_name, message_id)
                    if message:
                        messages.append(message)
                
                return messages
                
        except Exception as e:
            self.logger.error(f"Failed to list messages: {e}")
            return []
    
    async def update(self, message: DLQMessage) -> bool:
        """Update an existing message"""
        try:
            async with RedisClient() as client:
                # Get old message for status comparison
                old_message = await self.get(
                    message.queue_name, 
                    message.id
                )
                
                if not old_message:
                    return False
                
                # Update message data
                message_key = self._get_message_key(
                    message.queue_name,
                    message.id
                )
                
                success = await client.set_json(
                    message_key,
                    message.to_dict(),
                    expire=timedelta(days=self.ttl_days)
                )
                
                if success:
                    # Update status index if changed
                    if old_message.status != message.status:
                        await self._update_status_index(
                            client,
                            message.queue_name,
                            message.id,
                            message.status,
                            old_status=old_message.status
                        )
                    
                    # Update retry index
                    if message.next_retry_at:
                        await self._update_retry_index(
                            client,
                            message.queue_name,
                            message.id,
                            message.next_retry_at
                        )
                
                return success
                
        except Exception as e:
            self.logger.error(f"Failed to update message: {e}")
            return False
    
    async def delete(
        self, 
        queue_name: str, 
        message_id: str
    ) -> bool:
        """Delete a message from the DLQ"""
        try:
            async with RedisClient() as client:
                # Get message for status
                message = await self.get(queue_name, message_id)
                if not message:
                    return False
                
                # Delete message data
                message_key = self._get_message_key(queue_name, message_id)
                deleted = await client.client.delete(message_key)
                
                if deleted:
                    # Remove from queue
                    queue_key = RedisKeyPatterns.DLQ_MESSAGES.format(
                        queue_name=queue_name
                    )
                    await client.remove_from_sorted_set(
                        queue_key,
                        message_id
                    )
                    
                    # Remove from status index
                    status_key = self._get_status_key(
                        queue_name, 
                        message.status
                    )
                    await client.client.srem(status_key, message_id)
                    
                    # Remove from retry index
                    retry_key = self._get_retry_key(queue_name)
                    await client.remove_from_sorted_set(
                        retry_key,
                        message_id
                    )
                
                return bool(deleted)
                
        except Exception as e:
            self.logger.error(f"Failed to delete message: {e}")
            return False
    
    async def get_ready_for_retry(
        self,
        queue_name: str,
        limit: int = 10
    ) -> List[DLQMessage]:
        """Get messages ready for retry"""
        try:
            async with RedisClient() as client:
                retry_key = self._get_retry_key(queue_name)
                now = datetime.utcnow().timestamp()
                
                # Get messages with retry time <= now
                message_ids = await client.client.zrangebyscore(
                    retry_key,
                    0,
                    now,
                    start=0,
                    num=limit
                )
                
                # Fetch messages
                messages = []
                for message_id in message_ids:
                    message = await self.get(queue_name, message_id)
                    if message and message.status != MessageStatus.PROCESSING:
                        messages.append(message)
                
                return messages
                
        except Exception as e:
            self.logger.error(f"Failed to get retry messages: {e}")
            return []
    
    async def get_expired(
        self,
        queue_name: str,
        limit: int = 100
    ) -> List[DLQMessage]:
        """Get expired messages"""
        try:
            messages = await self.list_messages(
                queue_name,
                status=MessageStatus.PENDING,
                limit=limit
            )
            
            now = datetime.utcnow()
            expired = []
            
            for message in messages:
                if message.expired_at and message.expired_at <= now:
                    expired.append(message)
            
            return expired
            
        except Exception as e:
            self.logger.error(f"Failed to get expired messages: {e}")
            return []
    
    async def count_by_status(
        self,
        queue_name: str
    ) -> Dict[MessageStatus, int]:
        """Count messages by status"""
        try:
            async with RedisClient() as client:
                counts = {}
                
                for status in MessageStatus:
                    status_key = self._get_status_key(queue_name, status)
                    count = await client.client.scard(status_key)
                    counts[status] = count
                
                return counts
                
        except Exception as e:
            self.logger.error(f"Failed to count messages: {e}")
            return {}
    
    async def cleanup_old_messages(
        self,
        queue_name: str,
        older_than: datetime
    ) -> int:
        """Clean up old messages"""
        try:
            async with RedisClient() as client:
                queue_key = RedisKeyPatterns.DLQ_MESSAGES.format(
                    queue_name=queue_name
                )
                
                # Get old messages
                max_score = older_than.timestamp()
                old_message_ids = await client.client.zrangebyscore(
                    queue_key,
                    0,
                    max_score
                )
                
                # Delete each message
                deleted_count = 0
                for message_id in old_message_ids:
                    if await self.delete(queue_name, message_id):
                        deleted_count += 1
                
                return deleted_count
                
        except Exception as e:
            self.logger.error(f"Failed to cleanup messages: {e}")
            return 0
    
    def _get_message_key(self, queue_name: str, message_id: str) -> str:
        """Get Redis key for message data"""
        return f"dlq:message:{queue_name}:{message_id}"
    
    def _get_status_key(
        self, 
        queue_name: str, 
        status: MessageStatus
    ) -> str:
        """Get Redis key for status index"""
        return f"dlq:status:{queue_name}:{status.value}"
    
    def _get_retry_key(self, queue_name: str) -> str:
        """Get Redis key for retry index"""
        return f"dlq:retry:{queue_name}"
    
    async def _update_status_index(
        self,
        client: RedisClient,
        queue_name: str,
        message_id: str,
        new_status: MessageStatus,
        old_status: Optional[MessageStatus] = None
    ):
        """Update status index"""
        # Remove from old status
        if old_status:
            old_key = self._get_status_key(queue_name, old_status)
            await client.client.srem(old_key, message_id)
        
        # Add to new status
        new_key = self._get_status_key(queue_name, new_status)
        await client.client.sadd(new_key, message_id)
    
    async def _update_retry_index(
        self,
        client: RedisClient,
        queue_name: str,
        message_id: str,
        retry_at: datetime
    ):
        """Update retry index"""
        retry_key = self._get_retry_key(queue_name)
        score = retry_at.timestamp()
        await client.add_to_sorted_set(
            retry_key,
            message_id,
            score
        )