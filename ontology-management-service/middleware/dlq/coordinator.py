"""
DLQ coordinator - Facade for DLQ components
"""
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime, timedelta
import logging

from .models import (
    DLQMessage, MessageStatus, RetryConfig,
    DLQMetrics
)
from .storage.redis import RedisMessageStore
from .handler import DLQHandler
from .detector import PoisonMessageDetector
from .deduplicator import MessageDeduplicator
from ..common.metrics import MetricsCollector
from ..common.redis_utils import RedisKeyPatterns

logger = logging.getLogger(__name__)


class DLQCoordinator:
    """
    Facade for coordinating DLQ components
    """
    
    def __init__(
        self,
        default_config: Optional[RetryConfig] = None,
        dedup_window_seconds: int = 3600
    ):
        self.config = default_config or RetryConfig()
        
        # Components
        self.store = RedisMessageStore()
        self.handler = DLQHandler(self.store, self.config)
        self.detector = PoisonMessageDetector()
        self.deduplicator = MessageDeduplicator(dedup_window_seconds)
        self.metrics = MetricsCollector("dlq")
        
        # State
        self._retry_handlers: Dict[str, Callable] = {}
        self._processing_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_running = False
    
    def register_retry_handler(
        self,
        queue_name: str,
        handler: Callable
    ):
        """Register a retry handler for a queue"""
        self._retry_handlers[queue_name] = handler
        logger.info(f"Registered retry handler for queue: {queue_name}")
    
    async def start(self):
        """Start DLQ coordinator"""
        if self._is_running:
            logger.warning("DLQ coordinator already running")
            return
        
        self._is_running = True
        
        # Start background tasks
        self._processing_task = asyncio.create_task(
            self._processing_loop()
        )
        self._cleanup_task = asyncio.create_task(
            self._cleanup_loop()
        )
        
        logger.info("Started DLQ coordinator")
    
    async def stop(self):
        """Stop DLQ coordinator"""
        self._is_running = False
        
        # Cancel tasks
        for task in [self._processing_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        logger.info("Stopped DLQ coordinator")
    
    async def send_message(
        self,
        message_id: str,
        content: Dict[str, Any],
        reason: str,
        metadata: Optional[Dict[str, Any]] = None,
        queue_name: str = "default",
        original_queue: Optional[str] = None
    ) -> bool:
        """
        Send a message to DLQ (called by middleware coordinator)
        """
        try:
            # Check for duplicates
            content_hash = self.deduplicator.generate_hash(content)
            
            # Create temporary message for duplicate check
            temp_message = DLQMessage(
                id=message_id,
                queue_name=queue_name,
                original_queue=original_queue or queue_name,
                content=content,
                error_message=reason,
                content_hash=content_hash
            )
            
            if self.deduplicator.is_duplicate(temp_message, content_hash):
                self.metrics.increment_counter(
                    "dlq_duplicates_rejected_total",
                    labels={"queue": queue_name}
                )
                logger.info(f"Duplicate message rejected: {message_id}")
                return False
            
            # Send to DLQ
            message = await self.handler.send_to_dlq(
                queue_name=queue_name,
                original_queue=original_queue or queue_name,
                content=content,
                error_message=reason,
                metadata=metadata
            )
            
            # Store content hash
            message.content_hash = content_hash
            await self.store.update(message)
            
            # Check if poison
            is_poison, poison_reason = await self.detector.is_poison(
                message,
                self.config.poison_threshold
            )
            
            if is_poison:
                await self.handler.mark_as_poison(
                    queue_name,
                    message.id,
                    poison_reason
                )
            
            # Update metrics
            self.metrics.increment_counter(
                "dlq_messages_total",
                labels={
                    "queue": queue_name,
                    "status": message.status.value
                }
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send message to DLQ: {e}")
            return False
    
    async def get_queue_stats(
        self,
        queue_name: str = "default"
    ) -> Dict[str, Any]:
        """Get statistics for a DLQ queue"""
        # Get status counts
        status_counts = await self.store.count_by_status(queue_name)
        
        # Create metrics object
        metrics = DLQMetrics()
        metrics.update_status_count(status_counts)
        
        # Get additional stats
        return {
            "queue_name": queue_name,
            "total_messages": metrics.total_messages,
            "status_breakdown": {
                status.value: count 
                for status, count in status_counts.items()
            },
            "poison_rate": metrics.poison_rate,
            "retry_handlers_registered": queue_name in self._retry_handlers,
            "deduplicator_stats": self.deduplicator.get_stats()
        }
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get overall DLQ statistics"""
        # Get stats for all known queues
        queue_stats = {}
        
        for queue_name in self._retry_handlers.keys():
            queue_stats[queue_name] = await self.get_queue_stats(queue_name)
        
        # Add default queue if not already included
        if "default" not in queue_stats:
            queue_stats["default"] = await self.get_queue_stats("default")
        
        return {
            "is_running": self._is_running,
            "queues": queue_stats,
            "total_retry_handlers": len(self._retry_handlers),
            "config": {
                "max_retries": self.config.max_retries,
                "poison_threshold": self.config.poison_threshold,
                "strategy": self.config.strategy.value
            }
        }
    
    async def manually_retry(
        self,
        queue_name: str,
        message_id: str
    ) -> bool:
        """Manually retry a specific message"""
        handler = self._retry_handlers.get(queue_name)
        
        if not handler:
            logger.error(f"No retry handler for queue: {queue_name}")
            return False
        
        return await self.handler.retry_message(
            queue_name,
            message_id,
            handler
        )
    
    async def _processing_loop(self):
        """Background loop for processing retries"""
        while self._is_running:
            try:
                # Process each queue with a handler
                for queue_name, handler in self._retry_handlers.items():
                    result = await self.handler.process_retry_batch(
                        queue_name,
                        handler,
                        self.config.batch_size
                    )
                    
                    # Update metrics
                    if result["processed"] > 0:
                        self.metrics.increment_counter(
                            "dlq_retries_processed_total",
                            value=result["processed"],
                            labels={"queue": queue_name}
                        )
                        self.metrics.increment_counter(
                            "dlq_retries_succeeded_total",
                            value=result["succeeded"],
                            labels={"queue": queue_name}
                        )
                        self.metrics.increment_counter(
                            "dlq_retries_failed_total",
                            value=result["failed"],
                            labels={"queue": queue_name}
                        )
                
                # Wait before next batch
                await asyncio.sleep(self.config.batch_timeout_seconds)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}")
                await asyncio.sleep(10)
    
    async def _cleanup_loop(self):
        """Background loop for cleanup tasks"""
        while self._is_running:
            try:
                # Clean up expired messages
                for queue_name in list(self._retry_handlers.keys()) + ["default"]:
                    expired_count = await self.handler.cleanup_expired(
                        queue_name
                    )
                    
                    if expired_count > 0:
                        self.metrics.increment_counter(
                            "dlq_expired_messages_total",
                            value=expired_count,
                            labels={"queue": queue_name}
                        )
                
                # Clean up old messages beyond TTL
                cutoff = datetime.utcnow() - timedelta(
                    seconds=self.config.ttl_seconds * 2
                )
                
                for queue_name in list(self._retry_handlers.keys()) + ["default"]:
                    deleted = await self.store.cleanup_old_messages(
                        queue_name,
                        cutoff
                    )
                    
                    if deleted > 0:
                        logger.info(
                            f"Cleaned up {deleted} old messages from {queue_name}"
                        )
                
                # Clear detector/deduplicator caches
                self.detector.clear_cache()
                
                # Wait for next cleanup
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                await asyncio.sleep(60)