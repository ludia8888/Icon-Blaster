"""
Production-grade Dead Letter Queue (DLQ) implementation for Action Service
Implements retry logic, poison message handling, and recovery mechanisms
"""
import asyncio
import json
import logging
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import redis.asyncio as redis
from prometheus_client import Counter, Gauge, Histogram

from shared.infrastructure.nats_client import NATSClient

logger = logging.getLogger(__name__)

# Metrics
dlq_messages = Counter('dlq_messages_total', 'Total DLQ messages', ['queue', 'reason'])
dlq_retries = Counter('dlq_retry_attempts_total', 'DLQ retry attempts', ['queue', 'status'])
dlq_size = Gauge('dlq_size', 'Current DLQ size', ['queue'])
dlq_age = Histogram('dlq_message_age_seconds', 'Age of messages in DLQ', ['queue'])
dlq_processing_time = Histogram('dlq_processing_time_seconds', 'Time to process DLQ message', ['queue'])

class DLQReason(Enum):
    """Reasons for sending message to DLQ"""
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_FAILED = "execution_failed"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    PLUGIN_ERROR = "plugin_error"
    WEBHOOK_FAILED = "webhook_failed"
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    POISON_MESSAGE = "poison_message"
    UNKNOWN_ERROR = "unknown_error"

@dataclass
class DLQMessage:
    """Message structure for DLQ"""
    message_id: str
    queue_name: str
    original_message: Dict[str, Any]
    reason: DLQReason
    error_details: str
    stack_trace: Optional[str]
    retry_count: int
    max_retries: int
    first_failure_time: datetime
    last_failure_time: datetime
    next_retry_time: Optional[datetime]
    metadata: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        data = asdict(self)
        data['reason'] = self.reason.value
        data['first_failure_time'] = self.first_failure_time.isoformat()
        data['last_failure_time'] = self.last_failure_time.isoformat()
        data['next_retry_time'] = self.next_retry_time.isoformat() if self.next_retry_time else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DLQMessage':
        """Create from dictionary"""
        data['reason'] = DLQReason(data['reason'])
        data['first_failure_time'] = datetime.fromisoformat(data['first_failure_time'])
        data['last_failure_time'] = datetime.fromisoformat(data['last_failure_time'])
        if data.get('next_retry_time'):
            data['next_retry_time'] = datetime.fromisoformat(data['next_retry_time'])
        return cls(**data)

class RetryPolicy:
    """Configurable retry policy for DLQ messages"""

    def __init__(
        self,
        max_retries: int = 5,
        initial_delay: int = 60,  # seconds
        max_delay: int = 3600,    # 1 hour
        backoff_multiplier: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter

    def get_next_retry_time(self, retry_count: int) -> datetime:
        """Calculate next retry time based on retry count"""
        if retry_count >= self.max_retries:
            return None

        # Exponential backoff
        delay = min(
            self.initial_delay * (self.backoff_multiplier ** retry_count),
            self.max_delay
        )

        # Add jitter to prevent thundering herd
        if self.jitter:
            import random
            delay = delay * (0.5 + random.random())

        return datetime.utcnow() + timedelta(seconds=delay)

class DLQHandler:
    """Dead Letter Queue handler with advanced features"""

    def __init__(
        self,
        redis_client: redis.Redis,
        nats_client: Optional[NATSClient] = None,
        default_retry_policy: Optional[RetryPolicy] = None
    ):
        self.redis = redis_client
        self.nats = nats_client
        self.retry_policies: Dict[str, RetryPolicy] = {}
        self.default_retry_policy = default_retry_policy or RetryPolicy()
        self.processing_queues: Dict[str, asyncio.Queue] = {}
        self.message_handlers: Dict[str, Callable] = {}
        self._running = False
        self._tasks: List[asyncio.Task] = []

    def register_retry_policy(self, queue_name: str, policy: RetryPolicy):
        """Register custom retry policy for specific queue"""
        self.retry_policies[queue_name] = policy

    def register_handler(self, queue_name: str, handler: Callable):
        """Register message handler for retry processing"""
        self.message_handlers[queue_name] = handler

    def get_retry_policy(self, queue_name: str) -> RetryPolicy:
        """Get retry policy for queue"""
        return self.retry_policies.get(queue_name, self.default_retry_policy)

    async def send_to_dlq(
        self,
        queue_name: str,
        original_message: Dict[str, Any],
        reason: DLQReason,
        error: Exception,
        retry_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Send message to DLQ"""
        try:
            # Create DLQ message
            message_id = f"{queue_name}:{datetime.utcnow().timestamp()}:{hash(str(original_message))}"

            dlq_message = DLQMessage(
                message_id=message_id,
                queue_name=queue_name,
                original_message=original_message,
                reason=reason,
                error_details=str(error),
                stack_trace=traceback.format_exc() if error else None,
                retry_count=retry_count,
                max_retries=self.get_retry_policy(queue_name).max_retries,
                first_failure_time=datetime.utcnow(),
                last_failure_time=datetime.utcnow(),
                next_retry_time=self.get_retry_policy(queue_name).get_next_retry_time(retry_count),
                metadata=metadata or {}
            )

            # Store in Redis
            dlq_key = f"dlq:{queue_name}:{message_id}"
            await self.redis.set(
                dlq_key,
                json.dumps(dlq_message.to_dict()),
                ex=86400 * 7  # Keep for 7 days
            )

            # Add to queue index
            await self.redis.zadd(
                f"dlq:index:{queue_name}",
                {message_id: datetime.utcnow().timestamp()}
            )

            # Update metrics
            dlq_messages.labels(queue=queue_name, reason=reason.value).inc()
            await self._update_queue_size(queue_name)

            # Publish event if NATS available
            if self.nats:
                await self.nats.publish(
                    f"dlq.{queue_name}.message",
                    {
                        'message_id': message_id,
                        'reason': reason.value,
                        'retry_count': retry_count,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                )

            logger.warning(
                f"Message sent to DLQ - Queue: {queue_name}, Reason: {reason.value}, "
                f"Message ID: {message_id}, Retry Count: {retry_count}"
            )

            return message_id

        except Exception as e:
            logger.error(f"Failed to send message to DLQ: {e}")
            raise

    async def retry_message(self, queue_name: str, message_id: str) -> bool:
        """Manually retry a DLQ message"""
        try:
            # Get message from DLQ
            dlq_key = f"dlq:{queue_name}:{message_id}"
            message_data = await self.redis.get(dlq_key)

            if not message_data:
                logger.warning(f"DLQ message not found: {message_id}")
                return False

            dlq_message = DLQMessage.from_dict(json.loads(message_data))

            # Check if handler registered
            handler = self.message_handlers.get(queue_name)
            if not handler:
                logger.error(f"No handler registered for queue: {queue_name}")
                return False

            # Update retry count
            dlq_message.retry_count += 1
            dlq_message.last_failure_time = datetime.utcnow()

            try:
                # Execute handler
                start_time = asyncio.get_event_loop().time()
                await handler(dlq_message.original_message)

                # Success - remove from DLQ
                await self.remove_from_dlq(queue_name, message_id)

                # Update metrics
                dlq_retries.labels(queue=queue_name, status='success').inc()
                dlq_processing_time.labels(queue=queue_name).observe(
                    asyncio.get_event_loop().time() - start_time
                )

                logger.info(f"Successfully retried DLQ message: {message_id}")
                return True

            except Exception as retry_error:
                # Failed retry
                dlq_retries.labels(queue=queue_name, status='failure').inc()

                # Check if max retries exceeded
                if dlq_message.retry_count >= dlq_message.max_retries:
                    # Move to poison queue
                    await self.move_to_poison_queue(dlq_message)
                    await self.remove_from_dlq(queue_name, message_id)
                    logger.error(f"Message {message_id} moved to poison queue after {dlq_message.retry_count} retries")
                else:
                    # Update message with new retry time
                    dlq_message.next_retry_time = self.get_retry_policy(queue_name).get_next_retry_time(
                        dlq_message.retry_count
                    )
                    dlq_message.error_details = str(retry_error)
                    dlq_message.stack_trace = traceback.format_exc()

                    # Update in Redis
                    await self.redis.set(
                        dlq_key,
                        json.dumps(dlq_message.to_dict()),
                        ex=86400 * 7
                    )

                    logger.warning(
                        f"Retry failed for message {message_id}, "
                        f"retry count: {dlq_message.retry_count}/{dlq_message.max_retries}"
                    )

                return False

        except Exception as e:
            logger.error(f"Error retrying DLQ message: {e}")
            return False

    async def remove_from_dlq(self, queue_name: str, message_id: str):
        """Remove message from DLQ"""
        dlq_key = f"dlq:{queue_name}:{message_id}"
        await self.redis.delete(dlq_key)
        await self.redis.zrem(f"dlq:index:{queue_name}", message_id)
        await self._update_queue_size(queue_name)

    async def move_to_poison_queue(self, dlq_message: DLQMessage):
        """Move message to poison queue for manual intervention"""
        poison_key = f"poison:{dlq_message.queue_name}:{dlq_message.message_id}"

        # Mark as poison message
        dlq_message.reason = DLQReason.POISON_MESSAGE

        # Store in poison queue (no expiry)
        await self.redis.set(
            poison_key,
            json.dumps(dlq_message.to_dict())
        )

        # Add to poison index
        await self.redis.zadd(
            f"poison:index:{dlq_message.queue_name}",
            {dlq_message.message_id: datetime.utcnow().timestamp()}
        )

        # Alert operations team
        if self.nats:
            await self.nats.publish(
                "alerts.poison_message",
                {
                    'queue': dlq_message.queue_name,
                    'message_id': dlq_message.message_id,
                    'original_message': dlq_message.original_message,
                    'error_details': dlq_message.error_details,
                    'retry_count': dlq_message.retry_count,
                    'timestamp': datetime.utcnow().isoformat()
                }
            )

    async def get_dlq_messages(
        self,
        queue_name: str,
        limit: int = 100,
        include_expired: bool = False
    ) -> List[DLQMessage]:
        """Get messages from DLQ"""
        # Get message IDs from index
        if include_expired:
            message_ids = await self.redis.zrange(
                f"dlq:index:{queue_name}",
                0,
                limit - 1
            )
        else:
            # Only get messages ready for retry
            max_score = datetime.utcnow().timestamp()
            message_ids = await self.redis.zrangebyscore(
                f"dlq:index:{queue_name}",
                0,
                max_score,
                start=0,
                num=limit
            )

        messages = []
        for message_id in message_ids:
            dlq_key = f"dlq:{queue_name}:{message_id.decode() if isinstance(message_id, bytes) else message_id}"
            message_data = await self.redis.get(dlq_key)

            if message_data:
                try:
                    dlq_message = DLQMessage.from_dict(json.loads(message_data))

                    # Calculate message age
                    age = (datetime.utcnow() - dlq_message.first_failure_time).total_seconds()
                    dlq_age.labels(queue=queue_name).observe(age)

                    messages.append(dlq_message)
                except Exception as e:
                    logger.error(f"Error deserializing DLQ message: {e}")

        return messages

    async def start_retry_processor(self):
        """Start background retry processor"""
        if self._running:
            return

        self._running = True

        # Start processor for each registered queue
        for queue_name in self.message_handlers.keys():
            task = asyncio.create_task(self._process_queue_retries(queue_name))
            self._tasks.append(task)

        logger.info("DLQ retry processor started")

    async def stop_retry_processor(self):
        """Stop background retry processor"""
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

        logger.info("DLQ retry processor stopped")

    async def _process_queue_retries(self, queue_name: str):
        """Process retries for a specific queue"""
        logger.info(f"Starting retry processor for queue: {queue_name}")

        while self._running:
            try:
                # Get messages ready for retry
                messages = await self.get_dlq_messages(queue_name, limit=10, include_expired=False)

                for message in messages:
                    if message.next_retry_time and message.next_retry_time <= datetime.utcnow():
                        # Retry the message
                        asyncio.create_task(self.retry_message(queue_name, message.message_id))

                # Sleep before next check
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error in retry processor for queue {queue_name}: {e}")
                await asyncio.sleep(30)  # Back off on error

    async def _update_queue_size(self, queue_name: str):
        """Update queue size metric"""
        size = await self.redis.zcard(f"dlq:index:{queue_name}")
        dlq_size.labels(queue=queue_name).set(size)

    async def get_dlq_stats(self) -> Dict[str, Any]:
        """Get DLQ statistics"""
        stats = {
            'queues': {},
            'total_messages': 0,
            'total_poison_messages': 0
        }

        # Get all queue patterns
        queue_patterns = await self.redis.keys("dlq:index:*")

        for pattern in queue_patterns:
            queue_name = pattern.decode().replace("dlq:index:", "")
            queue_size = await self.redis.zcard(pattern)

            # Get poison queue size
            poison_size = await self.redis.zcard(f"poison:index:{queue_name}")

            stats['queues'][queue_name] = {
                'size': queue_size,
                'poison_size': poison_size
            }

            stats['total_messages'] += queue_size
            stats['total_poison_messages'] += poison_size

        return stats

# Specialized retry policies for different scenarios
WEBHOOK_RETRY_POLICY = RetryPolicy(
    max_retries=3,
    initial_delay=30,
    max_delay=300,
    backoff_multiplier=2.0
)

VALIDATION_RETRY_POLICY = RetryPolicy(
    max_retries=1,  # Validation errors rarely recover
    initial_delay=60,
    max_delay=60,
    backoff_multiplier=1.0
)

EXECUTION_RETRY_POLICY = RetryPolicy(
    max_retries=5,
    initial_delay=60,
    max_delay=1800,  # 30 minutes
    backoff_multiplier=3.0
)
