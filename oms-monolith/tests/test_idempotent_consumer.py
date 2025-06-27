"""
Tests for Idempotent Consumer functionality
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone
import uuid
from typing import Dict, Any

from models.idempotency import (
    EventEnvelope, IdempotencyKey, EventProcessingRecord,
    ConsumerState, IdempotentResult, calculate_state_hash
)
from core.idempotent.consumer_service import IdempotentConsumer
from core.idempotent.schema_event_consumer import (
    SchemaEventConsumer, SchemaState, EventResult
)


class TestIdempotencyModels:
    """Test idempotency model functionality"""
    
    def test_idempotency_key_generation(self):
        """Test idempotency key generation"""
        key = IdempotencyKey(
            event_id="evt_123",
            consumer_id="test_consumer",
            event_type="test.event"
        )
        
        composite_key = key.get_key()
        assert composite_key == "test_consumer:evt_123"
        
        hash_key = key.get_hash()
        assert len(hash_key) == 16  # Truncated hash
        assert all(c in '0123456789abcdef' for c in hash_key)
    
    def test_event_envelope_creation(self):
        """Test event envelope creation"""
        event = EventEnvelope(
            event_type="test.created",
            source_service="test_service",
            source_version="1.0.0",
            source_commit_hash="abc123",
            payload={"data": "test"}
        )
        
        assert event.event_id is not None
        assert event.event_id.startswith("evt_")
        assert event.correlation_id is not None
        assert event.created_at is not None
        
        # Test processing key
        processing_key = event.get_processing_key("consumer_1")
        assert processing_key == f"consumer_1:{event.event_id}"
        
        # Test payload hash
        payload_hash = event.calculate_payload_hash()
        assert len(payload_hash) == 64  # SHA256
    
    def test_consumer_state_update(self):
        """Test consumer state position update"""
        state = ConsumerState(
            consumer_id="test_consumer",
            consumer_version="1.0.0",
            state_commit_hash="initial_hash"
        )
        
        assert state.events_processed == 0
        assert state.last_processed_event_id is None
        
        # Update position
        state.update_position("evt_123", 10)
        
        assert state.events_processed == 1
        assert state.last_processed_event_id == "evt_123"
        assert state.last_sequence_number == 10
        assert state.last_processed_timestamp is not None


class SimpleState(dict):
    """Simple state for testing"""
    def __init__(self):
        super().__init__()
        self["counter"] = 0
        self["items"] = []


class TestIdempotentConsumer:
    """Test idempotent consumer functionality"""
    
    @pytest_asyncio.fixture
    async def consumer(self, tmp_path):
        """Create test consumer"""
        # Don't use the generic parameter, just create a plain consumer
        consumer = IdempotentConsumer(
            consumer_id="test_consumer",
            consumer_version="1.0.0",
            db_path=str(tmp_path / "test_consumer.db"),
            checkpoint_interval=5,
            state_class=dict  # Use dict directly
        )
        
        # Register test handler - return a simple dict, not EventResult
        async def increment_handler(event: EventEnvelope, state: dict) -> dict:
            if "counter" not in state:
                state["counter"] = 0
            if "items" not in state:
                state["items"] = []
            
            state["counter"] += event.payload.get("amount", 1)
            state["items"].append(event.event_id)
            
            # Return a dict that mimics EventResult structure
            return {
                "success": True,
                "new_state": state,
                "result": {"new_counter": state["counter"]},
                "side_effects": [f"Incremented counter by {event.payload.get('amount', 1)}"]
            }
        
        consumer.register_handler("counter.increment", increment_handler)
        
        await consumer.initialize()
        return consumer
    
    @pytest.mark.asyncio
    async def test_process_event_success(self, consumer):
        """Test successful event processing"""
        event = EventEnvelope(
            event_id="evt_test_1",
            event_type="counter.increment",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={"amount": 5}
        )
        
        result = await consumer.process_event(event)
        
        assert result.processed == True
        assert result.was_duplicate == False
        assert result.error is None
        assert result.processing_time_ms > 0
        assert len(result.side_effects) == 1
        
        # Check state was updated
        state = await consumer.get_state()
        print(f"State type: {type(state)}")
        print(f"State value: {state}")
        assert isinstance(state, dict), f"Expected dict, got {type(state)}"
        assert state["counter"] == 5
        assert "evt_test_1" in state["items"]
    
    @pytest.mark.asyncio
    async def test_idempotent_processing(self, consumer):
        """Test that duplicate events are not processed twice"""
        event = EventEnvelope(
            event_id="evt_duplicate",
            event_type="counter.increment",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={"amount": 10}
        )
        
        # Process once
        result1 = await consumer.process_event(event)
        assert result1.processed == True
        assert result1.was_duplicate == False
        
        state1 = await consumer.get_state()
        counter1 = state1["counter"]
        
        # Process again (should be skipped)
        result2 = await consumer.process_event(event)
        assert result2.processed == False
        assert result2.was_duplicate == True
        assert result2.previous_commit_hash == result1.previous_commit_hash
        assert result2.new_commit_hash == result1.new_commit_hash
        
        # State should not change
        state2 = await consumer.get_state()
        assert state2["counter"] == counter1
    
    @pytest.mark.asyncio
    async def test_commit_hash_tracking(self, consumer):
        """Test that commit hashes change with state changes"""
        initial_info = await consumer.get_consumer_info()
        initial_hash = initial_info.state_commit_hash
        
        # Process event that changes state
        event1 = EventEnvelope(
            event_id="evt_hash_1",
            event_type="counter.increment",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={"amount": 1}
        )
        
        result1 = await consumer.process_event(event1)
        assert result1.previous_commit_hash == initial_hash
        assert result1.new_commit_hash != initial_hash
        
        # Process another event
        event2 = EventEnvelope(
            event_id="evt_hash_2",
            event_type="counter.increment",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={"amount": 1}
        )
        
        result2 = await consumer.process_event(event2)
        assert result2.previous_commit_hash == result1.new_commit_hash
        assert result2.new_commit_hash != result2.previous_commit_hash
    
    @pytest.mark.asyncio
    async def test_batch_processing(self, consumer):
        """Test processing multiple events in order"""
        events = []
        for i in range(5):
            event = EventEnvelope(
                event_id=f"evt_batch_{i}",
                event_type="counter.increment",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={"amount": 1},
                sequence_number=i
            )
            events.append(event)
        
        results = await consumer.process_batch(events)
        
        assert len(results) == 5
        assert all(r.processed for r in results)
        assert all(not r.was_duplicate for r in results)
        
        # Check final state
        state = await consumer.get_state()
        assert state["counter"] == 5
        assert len(state["items"]) == 5
    
    @pytest.mark.asyncio
    async def test_checkpoint_creation(self, consumer):
        """Test automatic checkpoint creation"""
        # Process events up to checkpoint interval
        for i in range(6):  # Checkpoint interval is 5
            event = EventEnvelope(
                event_id=f"evt_checkpoint_{i}",
                event_type="counter.increment",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={"amount": 1}
            )
            await consumer.process_event(event)
        
        # Checkpoint should have been created after 5th event
        info = await consumer.get_consumer_info()
        assert info.events_processed == 6
        
        # Check that events_since_checkpoint reset
        assert consumer._events_since_checkpoint == 1  # 6th event


class TestSchemaEventConsumer:
    """Test schema event consumer"""
    
    @pytest_asyncio.fixture
    async def schema_consumer(self, tmp_path):
        """Create schema consumer for testing"""
        consumer = SchemaEventConsumer(
            consumer_id="test_schema_consumer",
            version="1.0.0"
        )
        # Override DB path
        consumer.consumer.db_path = str(tmp_path / "test_schema.db")
        await consumer.initialize()
        return consumer
    
    @pytest.mark.asyncio
    async def test_object_type_created(self, schema_consumer):
        """Test object type creation event"""
        event = EventEnvelope(
            event_type="object_type.created",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={
                "type_id": "Employee",
                "type_data": {
                    "name": "Employee",
                    "description": "Employee object type"
                }
            }
        )
        
        result = await schema_consumer.process_event(event)
        
        assert result.processed == True
        assert not result.was_duplicate
        
        # Check state
        state = await schema_consumer.get_state()
        assert state.total_object_types == 1
        assert "Employee" in state.object_types
        assert state.schema_version == 1
    
    @pytest.mark.asyncio
    async def test_object_type_updated(self, schema_consumer):
        """Test object type update event"""
        # First create
        create_event = EventEnvelope(
            event_type="object_type.created",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={
                "type_id": "Employee",
                "type_data": {"name": "Employee", "version": 1}
            }
        )
        await schema_consumer.process_event(create_event)
        
        # Then update
        update_event = EventEnvelope(
            event_type="object_type.updated",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={
                "type_id": "Employee",
                "type_data": {"version": 2},
                "changes": {"version": {"old": 1, "new": 2}}
            }
        )
        
        result = await schema_consumer.process_event(update_event)
        
        assert result.processed == True
        
        # Check state
        state = await schema_consumer.get_state()
        assert state.object_types["Employee"]["version"] == 2
        assert state.schema_version == 2  # Incremented twice
    
    @pytest.mark.asyncio
    async def test_schema_import(self, schema_consumer):
        """Test schema import event"""
        event = EventEnvelope(
            event_type="schema.imported",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={
                "object_types": {
                    "Employee": {"name": "Employee"},
                    "Department": {"name": "Department"},
                    "Project": {"name": "Project"}
                },
                "link_types": {
                    "works_in": {"name": "works_in"},
                    "manages": {"name": "manages"}
                }
            }
        )
        
        result = await schema_consumer.process_event(event)
        
        assert result.processed == True
        
        # Check state
        state = await schema_consumer.get_state()
        assert state.total_object_types == 3
        assert state.total_link_types == 2
        assert len(state.object_types) == 3
        assert len(state.link_types) == 2
    
    @pytest.mark.asyncio
    async def test_schema_reset(self, schema_consumer):
        """Test schema reset event"""
        # First add some types
        await schema_consumer.process_event(EventEnvelope(
            event_type="object_type.created",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={"type_id": "Test", "type_data": {}}
        ))
        
        # Then reset
        reset_event = EventEnvelope(
            event_type="schema.reset",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={}
        )
        
        result = await schema_consumer.process_event(reset_event)
        
        assert result.processed == True
        
        # Check state is cleared
        state = await schema_consumer.get_state()
        assert state.total_object_types == 0
        assert state.total_link_types == 0
        assert len(state.object_types) == 0
        assert state.schema_version == 0
    
    @pytest.mark.asyncio
    async def test_consumer_stats(self, schema_consumer):
        """Test getting consumer statistics"""
        # Process some events
        events = [
            EventEnvelope(
                event_type="object_type.created",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={"type_id": f"Type{i}", "type_data": {}}
            )
            for i in range(3)
        ]
        
        for event in events:
            await schema_consumer.process_event(event)
        
        # Get stats
        stats = await schema_consumer.get_stats()
        
        assert stats["consumer_id"] == "test_schema_consumer"
        assert stats["state"]["object_types"] == 3
        assert stats["processing"]["events_processed"] == 3
        assert stats["processing"]["events_failed"] == 0
        assert stats["health"]["is_healthy"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])