"""
Idempotent Consumer Service
Ensures exactly-once processing of events with commit hash tracking
"""
import asyncio
import json
import os
import time
from typing import Optional, Dict, Any, List, Callable, TypeVar, Generic
from datetime import datetime, timezone, timedelta

from models.idempotency import (
    IdempotencyKey, EventProcessingRecord, EventEnvelope,
    ConsumerState, IdempotentResult, ConsumerCheckpoint,
    calculate_state_hash, is_event_expired
)
from shared.database.sqlite_connector import SQLiteConnector, get_sqlite_connector
from utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class IdempotentConsumer(Generic[T]):
    """
    Generic idempotent consumer that ensures exactly-once processing
    """
    
    def __init__(
        self,
        consumer_id: str,
        consumer_version: str,
        db_path: Optional[str] = None,
        checkpoint_interval: int = 100,
        state_class: Optional[type] = None
    ):
        self.consumer_id = consumer_id
        self.consumer_version = consumer_version
        self.checkpoint_interval = checkpoint_interval
        self.state_class = state_class or dict
        
        self.db_name = f"idempotent_{consumer_id}.db"
        self.db_dir = db_path or os.path.join(
            os.path.dirname(__file__),
            "..", "..", "data"
        )
        
        self._connector: Optional[SQLiteConnector] = None
        self._initialized = False
        self._consumer_state: Optional[ConsumerState] = None
        self._processing_lock = asyncio.Lock()
        self._checkpoint_lock = asyncio.Lock()
        
        # Event handlers
        self._handlers: Dict[str, Callable] = {}
        
        # State
        self._current_state: Optional[T] = None
        self._events_since_checkpoint = 0
    
    async def initialize(self):
        """Initialize consumer database and state"""
        if self._initialized:
            return
        
        # Get or create connector
        self._connector = await get_sqlite_connector(
            self.db_name,
            db_dir=self.db_dir,
            enable_wal=True
        )
        
        # Define migrations
        migrations = [
            """
            CREATE TABLE IF NOT EXISTS processing_records (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                event_version INTEGER NOT NULL,
                consumer_id TEXT NOT NULL,
                consumer_version TEXT NOT NULL,
                input_commit_hash TEXT NOT NULL,
                output_commit_hash TEXT NOT NULL,
                processed_at TIMESTAMP NOT NULL,
                processing_duration_ms INTEGER NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                side_effects TEXT,  -- JSON array
                created_resources TEXT,  -- JSON array
                updated_resources TEXT,  -- JSON array
                idempotency_key TEXT NOT NULL,
                is_duplicate BOOLEAN DEFAULT FALSE,
                
                UNIQUE(idempotency_key)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_processed_at ON processing_records (processed_at)",
            "CREATE INDEX IF NOT EXISTS idx_status ON processing_records (status)",
            """
            CREATE TABLE IF NOT EXISTS consumer_state (
                consumer_id TEXT PRIMARY KEY,
                consumer_version TEXT NOT NULL,
                last_processed_event_id TEXT,
                last_processed_timestamp TIMESTAMP,
                last_sequence_number INTEGER,
                state_commit_hash TEXT NOT NULL,
                state_version INTEGER DEFAULT 0,
                events_processed INTEGER DEFAULT 0,
                events_skipped INTEGER DEFAULT 0,
                events_failed INTEGER DEFAULT 0,
                last_heartbeat TIMESTAMP NOT NULL,
                is_healthy BOOLEAN DEFAULT TRUE,
                error_count INTEGER DEFAULT 0,
                current_state TEXT  -- JSON serialized state
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                consumer_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                sequence_number INTEGER,
                timestamp TIMESTAMP NOT NULL,
                state_commit_hash TEXT NOT NULL,
                state_data TEXT,  -- JSON
                events_since_last INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_checkpoint_consumer ON checkpoints (consumer_id, created_at)",
            """
            CREATE TABLE IF NOT EXISTS replay_history (
                replay_id TEXT PRIMARY KEY,
                consumer_id TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                from_event_id TEXT,
                to_event_id TEXT,
                events_replayed INTEGER DEFAULT 0,
                events_skipped INTEGER DEFAULT 0,
                status TEXT NOT NULL,
                error_message TEXT
            )
            """
        ]
        
        # Initialize with migrations
        await self._connector.initialize(migrations=migrations)
        
        # Load or create consumer state
        await self._load_consumer_state()
        
        self._initialized = True
        logger.info(f"Idempotent consumer {self.consumer_id} initialized")
    
    async def _ensure_initialized(self):
        """Ensure database is initialized"""
        if not self._initialized:
            await self.initialize()
    
    def register_handler(self, event_type: str, handler: Callable):
        """Register event handler for specific event type"""
        self._handlers[event_type] = handler
        logger.info(f"Registered handler for {event_type}")
    
    async def process_event(self, event: EventEnvelope) -> IdempotentResult:
        """Process an event idempotently"""
        await self._ensure_initialized()
        start_time = time.time()
        
        # Check if event is expired
        if is_event_expired(event):
            logger.warning(f"Event {event.event_id} has expired")
            return IdempotentResult(
                processed=False,
                was_duplicate=False,
                error="Event expired",
                processing_time_ms=0,
                processor_version=self.consumer_version
            )
        
        # Check for duplicate processing
        idempotency_key = event.get_processing_key(self.consumer_id)
        
        async with self._processing_lock:
            # Check if already processed
            existing = await self._get_processing_record(event.event_id)
            if existing:
                logger.info(f"Event {event.event_id} already processed")
                return IdempotentResult(
                    processed=False,
                    was_duplicate=True,
                    previous_commit_hash=existing.input_commit_hash,
                    new_commit_hash=existing.output_commit_hash,
                    processing_time_ms=existing.processing_duration_ms,
                    processor_version=self.consumer_version
                )
            
            # Get handler
            handler = self._handlers.get(event.event_type)
            if not handler:
                logger.warning(f"No handler for event type {event.event_type}")
                return IdempotentResult(
                    processed=False,
                    was_duplicate=False,
                    error=f"No handler for {event.event_type}",
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    processor_version=self.consumer_version
                )
            
            # Calculate input state hash
            input_hash = self._consumer_state.state_commit_hash
            
            # Process event
            try:
                # Call handler with current state
                result = await handler(event, self._current_state)
                
                # Update state if handler returned new state
                if result:
                    if hasattr(result, 'new_state'):
                        self._current_state = result.new_state
                    elif isinstance(result, dict) and 'new_state' in result:
                        self._current_state = result['new_state']
                
                # Calculate output state hash
                output_hash = calculate_state_hash(
                    self._serialize_state(self._current_state)
                )
                
                # Record processing
                processing_time = max(1, int((time.time() - start_time) * 1000))
                
                record = EventProcessingRecord(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    event_version=event.event_version,
                    consumer_id=self.consumer_id,
                    consumer_version=self.consumer_version,
                    input_commit_hash=input_hash,
                    output_commit_hash=output_hash,
                    processing_duration_ms=processing_time,
                    status="success",
                    side_effects=result.side_effects if hasattr(result, 'side_effects') else (result.get('side_effects', []) if isinstance(result, dict) else []),
                    created_resources=result.created_resources if hasattr(result, 'created_resources') else (result.get('created_resources', []) if isinstance(result, dict) else []),
                    updated_resources=result.updated_resources if hasattr(result, 'updated_resources') else (result.get('updated_resources', []) if isinstance(result, dict) else []),
                    idempotency_key=idempotency_key,
                    is_duplicate=False
                )
                
                await self._save_processing_record(record)
                
                # Update consumer state
                self._consumer_state.state_commit_hash = output_hash
                self._consumer_state.state_version += 1
                self._consumer_state.update_position(
                    event.event_id,
                    event.sequence_number
                )
                
                await self._save_consumer_state()
                
                # Check if checkpoint needed
                self._events_since_checkpoint += 1
                if self._events_since_checkpoint >= self.checkpoint_interval:
                    await self._create_checkpoint()
                
                logger.info(
                    f"Processed event {event.event_id} "
                    f"({input_hash[:8]} -> {output_hash[:8]})"
                )
                
                return IdempotentResult(
                    processed=True,
                    was_duplicate=False,
                    previous_commit_hash=input_hash,
                    new_commit_hash=output_hash,
                    result=result.result if hasattr(result, 'result') else (result.get('result') if isinstance(result, dict) else None),
                    side_effects=record.side_effects,
                    processing_time_ms=processing_time,
                    processor_version=self.consumer_version
                )
                
            except Exception as e:
                logger.error(f"Error processing event {event.event_id}: {e}")
                
                # Record failure
                record = EventProcessingRecord(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    event_version=event.event_version,
                    consumer_id=self.consumer_id,
                    consumer_version=self.consumer_version,
                    input_commit_hash=input_hash,
                    output_commit_hash=input_hash,  # No state change on failure
                    processing_duration_ms=int((time.time() - start_time) * 1000),
                    status="failed",
                    error_message=str(e),
                    idempotency_key=idempotency_key,
                    is_duplicate=False
                )
                
                await self._save_processing_record(record)
                
                # Update failure count
                self._consumer_state.events_failed += 1
                self._consumer_state.error_count += 1
                
                if self._consumer_state.error_count > 5:
                    self._consumer_state.is_healthy = False
                
                await self._save_consumer_state()
                
                return IdempotentResult(
                    processed=False,
                    was_duplicate=False,
                    error=str(e),
                    should_retry=True,
                    processing_time_ms=record.processing_duration_ms,
                    processor_version=self.consumer_version
                )
    
    async def process_batch(self, events: List[EventEnvelope]) -> List[IdempotentResult]:
        """Process a batch of events"""
        results = []
        
        # Sort by sequence number if available
        sorted_events = sorted(
            events,
            key=lambda e: e.sequence_number or 0
        )
        
        for event in sorted_events:
            result = await self.process_event(event)
            results.append(result)
            
            # Stop on critical failure
            if result.error and not result.should_retry:
                break
        
        return results
    
    async def get_state(self) -> T:
        """Get current consumer state"""
        return self._current_state
    
    async def get_consumer_info(self) -> ConsumerState:
        """Get consumer metadata"""
        return self._consumer_state
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics (for generic consumers)"""
        return {
            "consumer_id": self._consumer_state.consumer_id,
            "consumer_version": self._consumer_state.consumer_version,
            "state": self._serialize_state(self._current_state),
            "processing": {
                "events_processed": self._consumer_state.events_processed,
                "events_skipped": self._consumer_state.events_skipped,
                "events_failed": self._consumer_state.events_failed,
                "last_event_id": self._consumer_state.last_processed_event_id,
                "last_processed": self._consumer_state.last_processed_timestamp.isoformat()
                    if self._consumer_state.last_processed_timestamp else None
            },
            "health": {
                "is_healthy": self._consumer_state.is_healthy,
                "error_count": self._consumer_state.error_count,
                "last_heartbeat": datetime.now(timezone.utc).isoformat()
            }
        }
    
    async def _load_consumer_state(self):
        """Load consumer state from database"""
        row = await self._connector.fetch_one(
            "SELECT * FROM consumer_state WHERE consumer_id = :consumer_id",
            {"consumer_id": self.consumer_id}
        )
            
        if row:
            # Load existing state
            self._consumer_state = ConsumerState(
                consumer_id=row['consumer_id'],
                consumer_version=row['consumer_version'],
                last_processed_event_id=row['last_processed_event_id'],
                last_processed_timestamp=datetime.fromisoformat(row['last_processed_timestamp'])
                    if row['last_processed_timestamp'] else None,
                last_sequence_number=row['last_sequence_number'],
                state_commit_hash=row['state_commit_hash'],
                state_version=row['state_version'],
                events_processed=row['events_processed'],
                events_skipped=row['events_skipped'],
                events_failed=row['events_failed'],
                is_healthy=bool(row['is_healthy']),
                error_count=row['error_count']
            )
            
            # Deserialize state
            if row['current_state']:
                state_data = json.loads(row['current_state'])
                self._current_state = self._deserialize_state(state_data)
            else:
                if self.state_class == dict:
                    self._current_state = {}
                else:
                    self._current_state = self.state_class()
        else:
            # Create new state
            if self.state_class == dict:
                initial_state = {}
            else:
                initial_state = self.state_class()
            state_hash = calculate_state_hash(
                self._serialize_state(initial_state)
            )
            
            self._consumer_state = ConsumerState(
                consumer_id=self.consumer_id,
                consumer_version=self.consumer_version,
                state_commit_hash=state_hash
            )
            
            self._current_state = initial_state
            
            # Save initial state
            await self._save_consumer_state()
    
    async def _save_consumer_state(self):
        """Save consumer state to database"""
        state_data = json.dumps(self._serialize_state(self._current_state))
        
        await self._connector.execute(
            """
            INSERT OR REPLACE INTO consumer_state (
                consumer_id, consumer_version, last_processed_event_id,
                last_processed_timestamp, last_sequence_number,
                state_commit_hash, state_version, events_processed,
                events_skipped, events_failed, last_heartbeat,
                is_healthy, error_count, current_state
            ) VALUES (
                :consumer_id, :consumer_version, :last_processed_event_id,
                :last_processed_timestamp, :last_sequence_number,
                :state_commit_hash, :state_version, :events_processed,
                :events_skipped, :events_failed, :last_heartbeat,
                :is_healthy, :error_count, :current_state
            )
            """,
            {
                "consumer_id": self._consumer_state.consumer_id,
                "consumer_version": self._consumer_state.consumer_version,
                "last_processed_event_id": self._consumer_state.last_processed_event_id,
                "last_processed_timestamp": self._consumer_state.last_processed_timestamp.isoformat()
                    if self._consumer_state.last_processed_timestamp else None,
                "last_sequence_number": self._consumer_state.last_sequence_number,
                "state_commit_hash": self._consumer_state.state_commit_hash,
                "state_version": self._consumer_state.state_version,
                "events_processed": self._consumer_state.events_processed,
                "events_skipped": self._consumer_state.events_skipped,
                "events_failed": self._consumer_state.events_failed,
                "last_heartbeat": datetime.now(timezone.utc).isoformat(),
                "is_healthy": self._consumer_state.is_healthy,
                "error_count": self._consumer_state.error_count,
                "current_state": state_data
            }
        )
    
    async def _get_processing_record(self, event_id: str) -> Optional[EventProcessingRecord]:
        """Get processing record for an event"""
        row = await self._connector.fetch_one(
            "SELECT * FROM processing_records WHERE event_id = :event_id",
            {"event_id": event_id}
        )
            
        if row:
            return EventProcessingRecord(
                event_id=row['event_id'],
                event_type=row['event_type'],
                event_version=row['event_version'],
                consumer_id=row['consumer_id'],
                consumer_version=row['consumer_version'],
                input_commit_hash=row['input_commit_hash'],
                output_commit_hash=row['output_commit_hash'],
                processed_at=datetime.fromisoformat(row['processed_at']),
                processing_duration_ms=row['processing_duration_ms'],
                status=row['status'],
                error_message=row['error_message'],
                retry_count=row['retry_count'],
                side_effects=json.loads(row['side_effects']) if row['side_effects'] else [],
                created_resources=json.loads(row['created_resources']) if row['created_resources'] else [],
                updated_resources=json.loads(row['updated_resources']) if row['updated_resources'] else [],
                idempotency_key=row['idempotency_key'],
                is_duplicate=bool(row['is_duplicate'])
            )
            
        return None
    
    async def _save_processing_record(self, record: EventProcessingRecord):
        """Save processing record"""
        await self._connector.execute(
            """
            INSERT INTO processing_records (
                event_id, event_type, event_version, consumer_id,
                consumer_version, input_commit_hash, output_commit_hash,
                processed_at, processing_duration_ms, status,
                error_message, retry_count, side_effects,
                created_resources, updated_resources,
                idempotency_key, is_duplicate
            ) VALUES (
                :event_id, :event_type, :event_version, :consumer_id,
                :consumer_version, :input_commit_hash, :output_commit_hash,
                :processed_at, :processing_duration_ms, :status,
                :error_message, :retry_count, :side_effects,
                :created_resources, :updated_resources,
                :idempotency_key, :is_duplicate
            )
            """,
            {
                "event_id": record.event_id,
                "event_type": record.event_type,
                "event_version": record.event_version,
                "consumer_id": record.consumer_id,
                "consumer_version": record.consumer_version,
                "input_commit_hash": record.input_commit_hash,
                "output_commit_hash": record.output_commit_hash,
                "processed_at": record.processed_at.isoformat(),
                "processing_duration_ms": record.processing_duration_ms,
                "status": record.status,
                "error_message": record.error_message,
                "retry_count": record.retry_count,
                "side_effects": json.dumps(record.side_effects),
                "created_resources": json.dumps(record.created_resources),
                "updated_resources": json.dumps(record.updated_resources),
                "idempotency_key": record.idempotency_key,
                "is_duplicate": record.is_duplicate
            }
        )
    
    async def _create_checkpoint(self):
        """Create a state checkpoint"""
        async with self._checkpoint_lock:
            checkpoint = ConsumerCheckpoint(
                consumer_id=self.consumer_id,
                event_id=self._consumer_state.last_processed_event_id,
                sequence_number=self._consumer_state.last_sequence_number,
                state_commit_hash=self._consumer_state.state_commit_hash,
                state_data=self._serialize_state(self._current_state),
                events_since_last=self._events_since_checkpoint
            )
            
            await self._connector.execute(
                """
                INSERT INTO checkpoints (
                    checkpoint_id, consumer_id, event_id,
                    sequence_number, timestamp, state_commit_hash,
                    state_data, events_since_last, created_at, expires_at
                ) VALUES (
                    :checkpoint_id, :consumer_id, :event_id,
                    :sequence_number, :timestamp, :state_commit_hash,
                    :state_data, :events_since_last, :created_at, :expires_at
                )
                """,
                {
                    "checkpoint_id": checkpoint.checkpoint_id,
                    "consumer_id": checkpoint.consumer_id,
                    "event_id": checkpoint.event_id,
                    "sequence_number": checkpoint.sequence_number,
                    "timestamp": checkpoint.timestamp.isoformat(),
                    "state_commit_hash": checkpoint.state_commit_hash,
                    "state_data": json.dumps(checkpoint.state_data),
                    "events_since_last": checkpoint.events_since_last,
                    "created_at": checkpoint.created_at.isoformat(),
                    "expires_at": checkpoint.expires_at.isoformat() if checkpoint.expires_at else None
                }
            )
            
            self._events_since_checkpoint = 0
            logger.info(f"Created checkpoint {checkpoint.checkpoint_id}")
    
    def _serialize_state(self, state: T) -> Dict[str, Any]:
        """Serialize state to dict"""
        if hasattr(state, 'model_dump'):
            # Pydantic v2
            return state.model_dump(mode='json')
        elif hasattr(state, 'dict'):
            # Pydantic v1
            data = state.dict()
            # Convert datetime objects
            return json.loads(json.dumps(data, default=str))
        elif hasattr(state, '__dict__'):
            return state.__dict__
        elif isinstance(state, dict):
            return state
        else:
            return {"value": state}
    
    def _deserialize_state(self, data: Dict[str, Any]) -> T:
        """Deserialize state from dict"""
        if self.state_class == dict:
            return data
        elif hasattr(self.state_class, 'model_validate'):
            return self.state_class.model_validate(data)
        elif hasattr(self.state_class, 'parse_obj'):
            return self.state_class.parse_obj(data)
        else:
            return self.state_class(**data)