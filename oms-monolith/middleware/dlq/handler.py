"""
Main DLQ handler implementation
"""
import asyncio
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import logging

from .models import (
    DLQMessage, MessageStatus, RetryConfig, 
    RetryStrategy
)
from .storage.base import MessageStore
from ..common.retry import calculate_delay

logger = logging.getLogger(__name__)


class DLQHandler:
    """Main handler for DLQ operations"""
    
    def __init__(
        self,
        message_store: MessageStore,
        default_config: Optional[RetryConfig] = None
    ):
        self.store = message_store
        self.config = default_config or RetryConfig()
        self.logger = logger
    
    async def send_to_dlq(
        self,
        queue_name: str,
        original_queue: str,
        content: Dict[str, Any],
        error_message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DLQMessage:
        """Send a failed message to DLQ"""
        # Create message
        message = DLQMessage(
            id=str(uuid.uuid4()),
            queue_name=queue_name,
            original_queue=original_queue,
            content=content,
            error_message=error_message,
            metadata=metadata or {}
        )
        
        # Calculate expiration
        message.expired_at = datetime.utcnow() + timedelta(
            seconds=self.config.ttl_seconds
        )
        
        # Calculate next retry time
        message.next_retry_at = self._calculate_next_retry(
            message.retry_count
        )
        
        # Store message
        success = await self.store.store(message)
        
        if success:
            self.logger.info(
                f"Message {message.id} sent to DLQ {queue_name}"
            )
        else:
            self.logger.error(
                f"Failed to store message {message.id} in DLQ"
            )
        
        return message
    
    async def retry_message(
        self,
        queue_name: str,
        message_id: str,
        retry_handler: callable
    ) -> bool:
        """Retry a DLQ message"""
        # Get message
        message = await self.store.get(queue_name, message_id)
        if not message:
            self.logger.error(f"Message {message_id} not found")
            return False
        
        # Check if message can be retried
        if message.status == MessageStatus.POISON:
            self.logger.warning(
                f"Cannot retry poison message {message_id}"
            )
            return False
        
        if message.retry_count >= self.config.max_retries:
            self.logger.warning(
                f"Message {message_id} exceeded max retries"
            )
            await self._mark_as_poison(message)
            return False
        
        # Update status
        message.status = MessageStatus.PROCESSING
        await self.store.update(message)
        
        try:
            # Execute retry handler
            result = await retry_handler(
                message.original_queue,
                message.content,
                message.metadata
            )
            
            if result:
                # Success - mark as completed
                message.status = MessageStatus.COMPLETED
                await self.store.update(message)
                
                self.logger.info(
                    f"Successfully retried message {message_id}"
                )
                return True
            else:
                # Failed - increment retry count
                await self._handle_retry_failure(message, "Retry failed")
                return False
                
        except Exception as e:
            # Exception - handle failure
            await self._handle_retry_failure(
                message, 
                f"Retry exception: {str(e)}"
            )
            return False
    
    async def process_retry_batch(
        self,
        queue_name: str,
        retry_handler: callable,
        batch_size: Optional[int] = None
    ) -> Dict[str, int]:
        """Process a batch of messages ready for retry"""
        batch_size = batch_size or self.config.batch_size
        
        # Get messages ready for retry
        messages = await self.store.get_ready_for_retry(
            queue_name,
            limit=batch_size
        )
        
        if not messages:
            return {"processed": 0, "succeeded": 0, "failed": 0}
        
        # Process messages concurrently
        tasks = [
            self.retry_message(queue_name, msg.id, retry_handler)
            for msg in messages
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count results
        succeeded = sum(1 for r in results if r is True)
        failed = len(results) - succeeded
        
        self.logger.info(
            f"Processed {len(messages)} messages: "
            f"{succeeded} succeeded, {failed} failed"
        )
        
        return {
            "processed": len(messages),
            "succeeded": succeeded,
            "failed": failed
        }
    
    async def get_message_status(
        self,
        queue_name: str,
        message_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get status of a DLQ message"""
        message = await self.store.get(queue_name, message_id)
        
        if not message:
            return None
        
        return {
            "id": message.id,
            "status": message.status.value,
            "retry_count": message.retry_count,
            "error_message": message.error_message,
            "created_at": message.created_at.isoformat(),
            "next_retry_at": (
                message.next_retry_at.isoformat() 
                if message.next_retry_at else None
            ),
            "error_history": message.error_history
        }
    
    async def requeue_message(
        self,
        queue_name: str,
        message_id: str
    ) -> bool:
        """Requeue a message for immediate retry"""
        message = await self.store.get(queue_name, message_id)
        
        if not message:
            return False
        
        # Reset for retry
        message.status = MessageStatus.PENDING
        message.next_retry_at = datetime.utcnow()
        
        return await self.store.update(message)
    
    async def mark_as_poison(
        self,
        queue_name: str,
        message_id: str,
        reason: Optional[str] = None
    ) -> bool:
        """Manually mark a message as poison"""
        message = await self.store.get(queue_name, message_id)
        
        if not message:
            return False
        
        message.mark_as_poison()
        
        if reason:
            message.add_error(f"Marked as poison: {reason}")
        
        return await self.store.update(message)
    
    async def cleanup_expired(
        self,
        queue_name: str,
        limit: int = 100
    ) -> int:
        """Clean up expired messages"""
        expired_messages = await self.store.get_expired(
            queue_name,
            limit
        )
        
        deleted_count = 0
        for message in expired_messages:
            # Mark as expired
            message.status = MessageStatus.EXPIRED
            await self.store.update(message)
            
            # Or delete if configured
            # if await self.store.delete(queue_name, message.id):
            #     deleted_count += 1
        
        if deleted_count > 0:
            self.logger.info(
                f"Cleaned up {deleted_count} expired messages"
            )
        
        return deleted_count
    
    def _calculate_next_retry(
        self,
        retry_count: int
    ) -> datetime:
        """Calculate next retry time based on strategy"""
        if self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = min(
                self.config.initial_delay_seconds * (
                    self.config.backoff_multiplier ** retry_count
                ),
                self.config.max_delay_seconds
            )
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = min(
                self.config.initial_delay_seconds * (retry_count + 1),
                self.config.max_delay_seconds
            )
        elif self.config.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.config.initial_delay_seconds
        else:  # IMMEDIATE
            delay = 0
        
        return datetime.utcnow() + timedelta(seconds=delay)
    
    async def _handle_retry_failure(
        self,
        message: DLQMessage,
        error: str
    ):
        """Handle retry failure"""
        message.increment_retry()
        message.add_error(error)
        
        # Check if should be marked as poison
        if message.retry_count >= self.config.poison_threshold:
            await self._mark_as_poison(message)
        else:
            # Set status and next retry
            message.status = MessageStatus.FAILED
            message.next_retry_at = self._calculate_next_retry(
                message.retry_count
            )
            await self.store.update(message)
    
    async def _mark_as_poison(self, message: DLQMessage):
        """Mark message as poison"""
        message.mark_as_poison()
        message.add_error(
            f"Marked as poison after {message.retry_count} retries"
        )
        
        # Move to poison queue if configured
        poison_key = RedisKeyPatterns.DLQ_POISON.format(
            queue_name=message.queue_name
        )
        
        await self.store.update(message)
        
        self.logger.error(
            f"Message {message.id} marked as poison"
        )