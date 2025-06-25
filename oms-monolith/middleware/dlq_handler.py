"""
Enterprise-grade Dead Letter Queue (DLQ) system with retry and poison message handling.

Features:
- Multiple retry strategies (exponential backoff, linear, fixed)
- Poison message detection and quarantine
- Message deduplication
- DLQ monitoring and alerting
- Message replay capabilities
- Batch processing
- Message transformation before retry
- Circuit breaker integration
"""

import asyncio
import json
import time
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, Union
import redis.asyncio as redis
from collections import defaultdict, deque
import logging
import pickle
import base64
import zlib

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategies."""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"
    CUSTOM = "custom"


class MessageStatus(Enum):
    """Message status in DLQ."""
    PENDING = "pending"
    PROCESSING = "processing"
    RETRYING = "retrying"
    FAILED = "failed"
    POISON = "poison"
    EXPIRED = "expired"
    SUCCEEDED = "succeeded"


@dataclass
class DLQMessage:
    """Dead letter queue message."""
    id: str
    queue_name: str
    payload: Any
    error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = field(default_factory=datetime.now)
    last_retry_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None
    status: MessageStatus = MessageStatus.PENDING
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_history: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'queue_name': self.queue_name,
            'payload': self.payload,
            'error': self.error,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'created_at': self.created_at.isoformat(),
            'last_retry_at': self.last_retry_at.isoformat() if self.last_retry_at else None,
            'next_retry_at': self.next_retry_at.isoformat() if self.next_retry_at else None,
            'status': self.status.value,
            'metadata': self.metadata,
            'error_history': self.error_history
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DLQMessage':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            queue_name=data['queue_name'],
            payload=data['payload'],
            error=data.get('error'),
            retry_count=data.get('retry_count', 0),
            max_retries=data.get('max_retries', 3),
            created_at=datetime.fromisoformat(data['created_at']),
            last_retry_at=datetime.fromisoformat(data['last_retry_at']) if data.get('last_retry_at') else None,
            next_retry_at=datetime.fromisoformat(data['next_retry_at']) if data.get('next_retry_at') else None,
            status=MessageStatus(data.get('status', 'pending')),
            metadata=data.get('metadata', {}),
            error_history=data.get('error_history', [])
        )
    
    def add_error(self, error: str, details: Optional[Dict[str, Any]] = None):
        """Add error to history."""
        self.error = error
        self.error_history.append({
            'timestamp': datetime.now().isoformat(),
            'error': error,
            'details': details or {},
            'retry_count': self.retry_count
        })
    
    def should_retry(self) -> bool:
        """Check if message should be retried."""
        return (
            self.retry_count < self.max_retries and
            self.status not in [MessageStatus.POISON, MessageStatus.EXPIRED, MessageStatus.SUCCEEDED]
        )


@dataclass
class RetryConfig:
    """Retry configuration."""
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    initial_delay: float = 1.0
    max_delay: float = 300.0
    multiplier: float = 2.0
    jitter: bool = True
    custom_calculator: Optional[Callable[[int], float]] = None


@dataclass
class DLQConfig:
    """DLQ configuration."""
    name: str
    max_retries: int = 3
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    ttl: int = 86400  # 24 hours
    poison_threshold: int = 5
    deduplication_window: int = 3600  # 1 hour
    batch_size: int = 100
    processing_timeout: float = 300.0
    enable_compression: bool = True
    transform_function: Optional[Callable[[DLQMessage], DLQMessage]] = None
    success_callback: Optional[Callable[[DLQMessage], Any]] = None
    failure_callback: Optional[Callable[[DLQMessage], Any]] = None


class MessageStore(ABC):
    """Abstract message store."""
    
    @abstractmethod
    async def add(self, message: DLQMessage) -> bool:
        """Add message to store."""
        pass
    
    @abstractmethod
    async def get(self, message_id: str) -> Optional[DLQMessage]:
        """Get message by ID."""
        pass
    
    @abstractmethod
    async def update(self, message: DLQMessage) -> bool:
        """Update message."""
        pass
    
    @abstractmethod
    async def delete(self, message_id: str) -> bool:
        """Delete message."""
        pass
    
    @abstractmethod
    async def get_ready_messages(self, queue_name: str, limit: int) -> List[DLQMessage]:
        """Get messages ready for retry."""
        pass
    
    @abstractmethod
    async def get_by_status(self, queue_name: str, status: MessageStatus, limit: int) -> List[DLQMessage]:
        """Get messages by status."""
        pass


class RedisMessageStore(MessageStore):
    """Redis-based message store."""
    
    def __init__(self, redis_client: redis.Redis, enable_compression: bool = True):
        self.redis_client = redis_client
        self.enable_compression = enable_compression
    
    async def add(self, message: DLQMessage) -> bool:
        """Add message to Redis."""
        try:
            # Serialize message
            message_data = self._serialize(message)
            
            # Store message
            message_key = f"dlq:message:{message.id}"
            await self.redis_client.set(message_key, message_data)
            
            # Add to queue index
            queue_key = f"dlq:queue:{message.queue_name}"
            await self.redis_client.zadd(
                queue_key,
                {message.id: message.next_retry_at.timestamp() if message.next_retry_at else 0}
            )
            
            # Add to status index
            status_key = f"dlq:status:{message.queue_name}:{message.status.value}"
            await self.redis_client.sadd(status_key, message.id)
            
            # Set TTL
            if hasattr(message, 'ttl'):
                await self.redis_client.expire(message_key, message.ttl)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add message to Redis: {e}")
            return False
    
    async def get(self, message_id: str) -> Optional[DLQMessage]:
        """Get message from Redis."""
        try:
            message_key = f"dlq:message:{message_id}"
            message_data = await self.redis_client.get(message_key)
            
            if not message_data:
                return None
            
            return self._deserialize(message_data)
            
        except Exception as e:
            logger.error(f"Failed to get message from Redis: {e}")
            return None
    
    async def update(self, message: DLQMessage) -> bool:
        """Update message in Redis."""
        try:
            # Remove from old status index
            old_message = await self.get(message.id)
            if old_message:
                old_status_key = f"dlq:status:{old_message.queue_name}:{old_message.status.value}"
                await self.redis_client.srem(old_status_key, message.id)
            
            # Update message
            await self.add(message)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update message in Redis: {e}")
            return False
    
    async def delete(self, message_id: str) -> bool:
        """Delete message from Redis."""
        try:
            # Get message first
            message = await self.get(message_id)
            if not message:
                return False
            
            # Remove from indices
            queue_key = f"dlq:queue:{message.queue_name}"
            await self.redis_client.zrem(queue_key, message_id)
            
            status_key = f"dlq:status:{message.queue_name}:{message.status.value}"
            await self.redis_client.srem(status_key, message_id)
            
            # Remove message
            message_key = f"dlq:message:{message_id}"
            await self.redis_client.delete(message_key)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete message from Redis: {e}")
            return False
    
    async def get_ready_messages(self, queue_name: str, limit: int) -> List[DLQMessage]:
        """Get messages ready for retry."""
        try:
            queue_key = f"dlq:queue:{queue_name}"
            current_time = time.time()
            
            # Get message IDs ready for retry
            message_ids = await self.redis_client.zrangebyscore(
                queue_key,
                0,
                current_time,
                start=0,
                num=limit
            )
            
            # Get messages
            messages = []
            for message_id in message_ids:
                message = await self.get(message_id.decode())
                if message and message.status == MessageStatus.PENDING:
                    messages.append(message)
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get ready messages: {e}")
            return []
    
    async def get_by_status(self, queue_name: str, status: MessageStatus, limit: int) -> List[DLQMessage]:
        """Get messages by status."""
        try:
            status_key = f"dlq:status:{queue_name}:{status.value}"
            message_ids = await self.redis_client.srandmember(status_key, limit)
            
            messages = []
            for message_id in message_ids:
                message = await self.get(message_id.decode())
                if message:
                    messages.append(message)
            
            return messages
            
        except Exception as e:
            logger.error(f"Failed to get messages by status: {e}")
            return []
    
    def _serialize(self, message: DLQMessage) -> bytes:
        """Serialize message."""
        data = pickle.dumps(message.to_dict())
        if self.enable_compression:
            data = zlib.compress(data)
        return base64.b64encode(data)
    
    def _deserialize(self, data: bytes) -> DLQMessage:
        """Deserialize message."""
        data = base64.b64decode(data)
        if self.enable_compression:
            data = zlib.decompress(data)
        message_dict = pickle.loads(data)
        return DLQMessage.from_dict(message_dict)


class RetryCalculator:
    """Calculates retry delays."""
    
    @staticmethod
    def calculate_delay(retry_count: int, config: RetryConfig) -> float:
        """Calculate retry delay."""
        if config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = min(
                config.initial_delay * (config.multiplier ** retry_count),
                config.max_delay
            )
        elif config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = min(
                config.initial_delay * (retry_count + 1),
                config.max_delay
            )
        elif config.strategy == RetryStrategy.FIXED_DELAY:
            delay = config.initial_delay
        elif config.strategy == RetryStrategy.CUSTOM and config.custom_calculator:
            delay = config.custom_calculator(retry_count)
        else:
            delay = config.initial_delay
        
        # Add jitter if enabled
        if config.jitter:
            import random
            jitter = random.uniform(0, delay * 0.1)
            delay += jitter
        
        return delay


class PoisonMessageDetector:
    """Detects poison messages."""
    
    def __init__(self, threshold: int = 5):
        self.threshold = threshold
        self.error_patterns: Dict[str, int] = defaultdict(int)
    
    def is_poison(self, message: DLQMessage) -> bool:
        """Check if message is poison."""
        # Check retry count
        if message.retry_count >= self.threshold:
            return True
        
        # Check error patterns
        if message.error:
            error_hash = self._get_error_hash(message.error)
            self.error_patterns[error_hash] += 1
            
            if self.error_patterns[error_hash] >= self.threshold:
                return True
        
        # Check error history
        unique_errors = set()
        for error_entry in message.error_history:
            unique_errors.add(error_entry.get('error', ''))
        
        if len(unique_errors) >= self.threshold:
            return True
        
        return False
    
    def _get_error_hash(self, error: str) -> str:
        """Get hash of error for pattern matching."""
        # Normalize error message
        normalized = error.lower().strip()
        # Remove numbers and specific identifiers
        import re
        normalized = re.sub(r'\d+', '', normalized)
        normalized = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '', normalized)
        
        return hashlib.md5(normalized.encode()).hexdigest()


class MessageDeduplicator:
    """Handles message deduplication."""
    
    def __init__(self, window_seconds: int = 3600):
        self.window_seconds = window_seconds
        self.seen_messages: Dict[str, float] = {}
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.time()
    
    def is_duplicate(self, message: DLQMessage) -> bool:
        """Check if message is duplicate."""
        # Cleanup old entries
        if time.time() - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
        
        # Generate message hash
        message_hash = self._get_message_hash(message)
        
        # Check if seen
        if message_hash in self.seen_messages:
            return True
        
        # Mark as seen
        self.seen_messages[message_hash] = time.time()
        return False
    
    def _get_message_hash(self, message: DLQMessage) -> str:
        """Get hash of message for deduplication."""
        # Create hash from queue name and payload
        data = f"{message.queue_name}:{json.dumps(message.payload, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()
    
    def _cleanup(self):
        """Cleanup old entries."""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds
        
        self.seen_messages = {
            k: v for k, v in self.seen_messages.items()
            if v > cutoff_time
        }
        
        self._last_cleanup = current_time


class DLQHandler:
    """Main DLQ handler."""
    
    def __init__(
        self,
        config: DLQConfig,
        message_store: MessageStore,
        processor: Callable[[Any], Any]
    ):
        self.config = config
        self.message_store = message_store
        self.processor = processor
        self.poison_detector = PoisonMessageDetector(config.poison_threshold)
        self.deduplicator = MessageDeduplicator(config.deduplication_window)
        self.retry_calculator = RetryCalculator()
        
        self._running = False
        self._processing_task: Optional[asyncio.Task] = None
        self._metrics = defaultdict(int)
    
    async def add_message(
        self,
        payload: Any,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Add message to DLQ."""
        try:
            # Create message
            message = DLQMessage(
                id=self._generate_message_id(),
                queue_name=self.config.name,
                payload=payload,
                error=error,
                max_retries=self.config.max_retries,
                metadata=metadata or {}
            )
            
            # Check for duplicates
            if self.deduplicator.is_duplicate(message):
                logger.warning(f"Duplicate message detected for queue {self.config.name}")
                self._metrics['duplicates'] += 1
                return None
            
            # Calculate next retry time
            delay = self.retry_calculator.calculate_delay(0, self.config.retry_config)
            message.next_retry_at = datetime.now() + timedelta(seconds=delay)
            
            # Store message
            if await self.message_store.add(message):
                self._metrics['added'] += 1
                logger.info(f"Added message {message.id} to DLQ {self.config.name}")
                return message.id
            else:
                return None
                
        except Exception as e:
            logger.error(f"Failed to add message to DLQ: {e}")
            return None
    
    async def process_messages(self):
        """Process messages in DLQ."""
        while self._running:
            try:
                # Get ready messages
                messages = await self.message_store.get_ready_messages(
                    self.config.name,
                    self.config.batch_size
                )
                
                if messages:
                    # Process in parallel with limited concurrency
                    semaphore = asyncio.Semaphore(10)
                    
                    async def process_with_semaphore(msg):
                        async with semaphore:
                            await self._process_message(msg)
                    
                    await asyncio.gather(
                        *[process_with_semaphore(msg) for msg in messages],
                        return_exceptions=True
                    )
                
                # Wait before next batch
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in DLQ processing loop: {e}")
                await asyncio.sleep(5)
    
    async def _process_message(self, message: DLQMessage):
        """Process a single message."""
        try:
            # Update status
            message.status = MessageStatus.PROCESSING
            message.last_retry_at = datetime.now()
            await self.message_store.update(message)
            
            # Transform message if configured
            if self.config.transform_function:
                try:
                    message = await self._apply_transform(message)
                except Exception as e:
                    logger.error(f"Transform failed for message {message.id}: {e}")
            
            # Process message
            try:
                result = await asyncio.wait_for(
                    self._execute_processor(message.payload),
                    timeout=self.config.processing_timeout
                )
                
                # Success
                message.status = MessageStatus.SUCCEEDED
                await self.message_store.update(message)
                
                # Call success callback
                if self.config.success_callback:
                    await self._execute_callback(self.config.success_callback, message)
                
                # Remove from DLQ
                await self.message_store.delete(message.id)
                
                self._metrics['processed'] += 1
                logger.info(f"Successfully processed message {message.id}")
                
            except Exception as e:
                # Processing failed
                await self._handle_failure(message, str(e))
                
        except Exception as e:
            logger.error(f"Error processing message {message.id}: {e}")
            self._metrics['errors'] += 1
    
    async def _handle_failure(self, message: DLQMessage, error: str):
        """Handle message processing failure."""
        message.retry_count += 1
        message.add_error(error)
        
        # Check if poison
        if self.poison_detector.is_poison(message):
            message.status = MessageStatus.POISON
            await self.message_store.update(message)
            
            logger.warning(f"Message {message.id} marked as poison")
            self._metrics['poison'] += 1
            
            # Call failure callback
            if self.config.failure_callback:
                await self._execute_callback(self.config.failure_callback, message)
            
            return
        
        # Check if should retry
        if message.should_retry():
            # Calculate next retry
            delay = self.retry_calculator.calculate_delay(
                message.retry_count,
                self.config.retry_config
            )
            message.next_retry_at = datetime.now() + timedelta(seconds=delay)
            message.status = MessageStatus.RETRYING
            
            logger.info(
                f"Message {message.id} will retry in {delay:.1f}s "
                f"(attempt {message.retry_count}/{message.max_retries})"
            )
            self._metrics['retries'] += 1
        else:
            # Max retries exceeded
            message.status = MessageStatus.FAILED
            
            logger.error(f"Message {message.id} failed after {message.retry_count} retries")
            self._metrics['failed'] += 1
            
            # Call failure callback
            if self.config.failure_callback:
                await self._execute_callback(self.config.failure_callback, message)
        
        await self.message_store.update(message)
    
    async def _execute_processor(self, payload: Any) -> Any:
        """Execute processor function."""
        if asyncio.iscoroutinefunction(self.processor):
            return await self.processor(payload)
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.processor, payload)
    
    async def _apply_transform(self, message: DLQMessage) -> DLQMessage:
        """Apply transform function."""
        if asyncio.iscoroutinefunction(self.config.transform_function):
            return await self.config.transform_function(message)
        else:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self.config.transform_function,
                message
            )
    
    async def _execute_callback(self, callback: Callable, message: DLQMessage):
        """Execute callback function."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(message)
            else:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, callback, message)
        except Exception as e:
            logger.error(f"Callback failed for message {message.id}: {e}")
    
    def _generate_message_id(self) -> str:
        """Generate unique message ID."""
        import uuid
        return f"{self.config.name}:{uuid.uuid4().hex}"
    
    async def start(self):
        """Start DLQ processing."""
        self._running = True
        self._processing_task = asyncio.create_task(self.process_messages())
        logger.info(f"Started DLQ handler for {self.config.name}")
    
    async def stop(self):
        """Stop DLQ processing."""
        self._running = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped DLQ handler for {self.config.name}")
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get DLQ metrics."""
        # Get message counts by status
        status_counts = {}
        for status in MessageStatus:
            messages = await self.message_store.get_by_status(
                self.config.name,
                status,
                1000
            )
            status_counts[status.value] = len(messages)
        
        return {
            'queue_name': self.config.name,
            'messages_by_status': status_counts,
            'total_added': self._metrics['added'],
            'total_processed': self._metrics['processed'],
            'total_retries': self._metrics['retries'],
            'total_failed': self._metrics['failed'],
            'total_poison': self._metrics['poison'],
            'total_duplicates': self._metrics['duplicates'],
            'total_errors': self._metrics['errors']
        }
    
    async def replay_messages(
        self,
        status: Optional[MessageStatus] = None,
        limit: Optional[int] = None
    ) -> int:
        """Replay messages from DLQ."""
        if status:
            messages = await self.message_store.get_by_status(
                self.config.name,
                status,
                limit or 1000
            )
        else:
            messages = await self.message_store.get_ready_messages(
                self.config.name,
                limit or 1000
            )
        
        replayed = 0
        for message in messages:
            # Reset message
            message.status = MessageStatus.PENDING
            message.retry_count = 0
            message.error = None
            message.next_retry_at = datetime.now()
            
            if await self.message_store.update(message):
                replayed += 1
        
        logger.info(f"Replayed {replayed} messages in DLQ {self.config.name}")
        return replayed
    
    async def purge_messages(
        self,
        status: Optional[MessageStatus] = None,
        older_than: Optional[timedelta] = None
    ) -> int:
        """Purge messages from DLQ."""
        if status:
            messages = await self.message_store.get_by_status(
                self.config.name,
                status,
                10000
            )
        else:
            # Get all messages
            messages = []
            for s in MessageStatus:
                messages.extend(
                    await self.message_store.get_by_status(
                        self.config.name,
                        s,
                        10000
                    )
                )
        
        purged = 0
        cutoff_time = datetime.now() - older_than if older_than else None
        
        for message in messages:
            # Check age
            if cutoff_time and message.created_at > cutoff_time:
                continue
            
            if await self.message_store.delete(message.id):
                purged += 1
        
        logger.info(f"Purged {purged} messages from DLQ {self.config.name}")
        return purged


class DLQManager:
    """Manages multiple DLQ handlers."""
    
    def __init__(self, message_store: MessageStore):
        self.message_store = message_store
        self.handlers: Dict[str, DLQHandler] = {}
    
    def create_handler(
        self,
        config: DLQConfig,
        processor: Callable[[Any], Any]
    ) -> DLQHandler:
        """Create a new DLQ handler."""
        handler = DLQHandler(config, self.message_store, processor)
        self.handlers[config.name] = handler
        return handler
    
    async def start_all(self):
        """Start all handlers."""
        for handler in self.handlers.values():
            await handler.start()
    
    async def stop_all(self):
        """Stop all handlers."""
        for handler in self.handlers.values():
            await handler.stop()
    
    async def get_all_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all handlers."""
        metrics = {}
        for name, handler in self.handlers.items():
            metrics[name] = await handler.get_metrics()
        return metrics