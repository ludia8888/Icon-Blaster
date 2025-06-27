"""
Real tests for idempotent consumer - no mocks, no shortcuts
"""
import pytest
import asyncio
import os
import time
from datetime import datetime, timezone
from typing import List

from models.idempotency import EventEnvelope, generate_event_id
from core.idempotent.schema_event_consumer import get_schema_consumer
from core.idempotent.consumer_service import IdempotentConsumer


class TestIdempotentRealWorld:
    """Real-world tests for idempotent consumer"""
    
    @pytest.mark.asyncio
    async def test_concurrent_duplicate_processing(self):
        """Test that concurrent duplicate events are properly handled"""
        consumer = await get_schema_consumer()
        
        # Create an event with unique ID based on timestamp
        import time
        unique_id = f"concurrent_test_{int(time.time() * 1000000)}"
        
        event = EventEnvelope(
            event_id=unique_id,
            event_type="object_type.created",
            source_service="test",
            source_version="1.0.0", 
            source_commit_hash="abc123",
            payload={
                "type_id": f"ConcurrentType_{unique_id}",
                "type_data": {"name": "ConcurrentType"}
            }
        )
        
        # Process the same event concurrently
        async def process_event():
            return await consumer.process_event(event)
        
        # Run 10 concurrent attempts
        tasks = [process_event() for _ in range(10)]
        results = await asyncio.gather(*tasks)
        
        # Only one should have been processed
        processed_count = sum(1 for r in results if r.processed)
        duplicate_count = sum(1 for r in results if r.was_duplicate)
        
        assert processed_count == 1, f"Expected 1 processed, got {processed_count}"
        assert duplicate_count == 9, f"Expected 9 duplicates, got {duplicate_count}"
        
        # All results should have the same commit hashes
        first_result = next(r for r in results if r.processed)
        for result in results:
            if result.was_duplicate:
                assert result.new_commit_hash == first_result.new_commit_hash
    
    @pytest.mark.asyncio
    async def test_state_recovery_after_crash(self, tmp_path):
        """Test that consumer state is properly recovered after a crash"""
        db_path = str(tmp_path / "test_recovery.db")
        
        # First consumer instance
        consumer1 = IdempotentConsumer(
            consumer_id="crash_test",
            consumer_version="1.0.0",
            db_path=db_path,
            state_class=dict
        )
        
        # Register handler
        async def handler(event, state):
            if "count" not in state:
                state["count"] = 0
            state["count"] += 1
            return {"success": True, "new_state": state}
        
        consumer1.register_handler("test.event", handler)
        await consumer1.initialize()
        
        # Process some events
        for i in range(5):
            event = EventEnvelope(
                event_type="test.event",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={"index": i}
            )
            await consumer1.process_event(event)
        
        state1 = await consumer1.get_state()
        info1 = await consumer1.get_consumer_info()
        
        # Simulate crash - create new consumer instance with same ID
        consumer2 = IdempotentConsumer(
            consumer_id="crash_test",
            consumer_version="1.0.0",
            db_path=db_path,
            state_class=dict
        )
        consumer2.register_handler("test.event", handler)
        await consumer2.initialize()
        
        # State should be recovered
        state2 = await consumer2.get_state()
        info2 = await consumer2.get_consumer_info()
        
        assert state2["count"] == 5
        assert info2.events_processed == 5
        assert info2.state_commit_hash == info1.state_commit_hash
    
    @pytest.mark.asyncio
    async def test_checkpoint_performance(self, tmp_path):
        """Test checkpoint creation and performance impact"""
        db_path = str(tmp_path / "test_checkpoint.db")
        
        consumer = IdempotentConsumer(
            consumer_id="checkpoint_test",
            consumer_version="1.0.0",
            db_path=db_path,
            checkpoint_interval=10,  # Checkpoint every 10 events
            state_class=dict
        )
        
        async def handler(event, state):
            if "events" not in state:
                state["events"] = []
            state["events"].append(event.event_id)
            return {"success": True, "new_state": state}
        
        consumer.register_handler("test.event", handler)
        await consumer.initialize()
        
        # Process 100 events and measure time
        start_time = time.time()
        checkpoint_times = []
        
        for i in range(100):
            event = EventEnvelope(
                event_type="test.event",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={"index": i}
            )
            
            event_start = time.time()
            await consumer.process_event(event)
            event_time = time.time() - event_start
            
            # Every 10th event should trigger a checkpoint
            if (i + 1) % 10 == 0:
                checkpoint_times.append(event_time)
        
        total_time = time.time() - start_time
        
        # Verify checkpoints were created
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM checkpoints")
            checkpoint_count = (await cursor.fetchone())[0]
        
        assert checkpoint_count == 10  # Should have 10 checkpoints
        
        # Checkpoint events shouldn't take significantly longer
        avg_checkpoint_time = sum(checkpoint_times) / len(checkpoint_times)
        avg_event_time = total_time / 100
        
        # Checkpoint overhead should be less than 5x normal event time
        assert avg_checkpoint_time < avg_event_time * 5
    
    @pytest.mark.asyncio
    async def test_real_database_persistence(self, tmp_path):
        """Test that data is really persisted to SQLite"""
        db_path = str(tmp_path / "test_persistence.db")
        
        # Process events
        consumer = IdempotentConsumer(
            consumer_id="persistence_test",
            consumer_version="1.0.0",
            db_path=db_path,
            state_class=dict
        )
        
        async def handler(event, state):
            state["last_event"] = event.event_id
            return {"success": True, "new_state": state}
        
        consumer.register_handler("test.event", handler)
        await consumer.initialize()
        
        event = EventEnvelope(
            event_id="persist_test_123",
            event_type="test.event",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={"data": "test"}
        )
        
        result = await consumer.process_event(event)
        assert result.processed
        
        # Directly query the database
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            # Check processing record
            cursor = await db.execute(
                "SELECT * FROM processing_records WHERE event_id = ?",
                (event.event_id,)
            )
            record = await cursor.fetchone()
            assert record is not None
            
            # Check consumer state
            cursor = await db.execute(
                "SELECT current_state FROM consumer_state WHERE consumer_id = ?",
                (consumer.consumer_id,)
            )
            state_json = (await cursor.fetchone())[0]
            import json
            state = json.loads(state_json)
            assert state["last_event"] == event.event_id
    
    @pytest.mark.asyncio
    async def test_error_recovery_and_retry(self):
        """Test error handling and retry logic"""
        consumer = await get_schema_consumer()
        
        # Create an event with invalid data that will cause an error
        invalid_event = EventEnvelope(
            event_type="object_type.created",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={
                # Missing required "type_id"
                "type_data": {"name": "Invalid"}
            }
        )
        
        # Should handle the error gracefully
        result = await consumer.process_event(invalid_event)
        assert not result.processed
        assert result.error is not None
        assert "type_id" in result.error
        
        # State should not have changed
        state = await consumer.get_state()
        initial_version = state.schema_version
        
        # Fix the event and retry with DIFFERENT event ID (simulating retry)
        fixed_event = EventEnvelope(
            # Different event ID - this is a new attempt, not the same event
            event_type="object_type.created",
            source_service="test",
            source_version="1.0.0",
            source_commit_hash="test123",
            payload={
                "type_id": "FixedType",
                "type_data": {"name": "Fixed"}
            }
        )
        
        # Should process successfully now
        result2 = await consumer.process_event(fixed_event)
        assert result2.processed
        assert result2.error is None
        
        # State should have changed
        state2 = await consumer.get_state()
        assert state2.schema_version == initial_version + 1
        assert "FixedType" in state2.object_types
    
    @pytest.mark.asyncio
    async def test_out_of_order_event_processing(self):
        """Test handling of out-of-order events"""
        consumer = await get_schema_consumer()
        
        # Create events with sequence numbers
        events = []
        for i in [2, 0, 3, 1, 4]:  # Out of order
            event = EventEnvelope(
                event_type="object_type.created",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={
                    "type_id": f"Type{i}",
                    "type_data": {"name": f"Type{i}", "order": i}
                },
                sequence_number=i
            )
            events.append(event)
        
        # Process out of order
        results = []
        for event in events:
            result = await consumer.process_event(event)
            results.append(result)
        
        # All should be processed
        assert all(r.processed for r in results)
        
        # State should contain all types
        state = await consumer.get_state()
        for i in range(5):
            assert f"Type{i}" in state.object_types
            assert state.object_types[f"Type{i}"]["order"] == i
    
    @pytest.mark.asyncio
    async def test_consumer_health_monitoring(self):
        """Test consumer health tracking"""
        consumer = await get_schema_consumer()
        
        # Get initial stats
        stats1 = await consumer.get_stats()
        assert stats1["health"]["is_healthy"]
        initial_processed = stats1["processing"]["events_processed"]
        initial_failed = stats1["processing"]["events_failed"]
        
        # Process some successful events
        for i in range(3):
            event = EventEnvelope(
                event_type="object_type.created",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={
                    "type_id": f"HealthType{i}",
                    "type_data": {"name": f"HealthType{i}"}
                }
            )
            await consumer.process_event(event)
        
        # Stats should show success
        stats2 = await consumer.get_stats()
        assert stats2["processing"]["events_processed"] >= initial_processed + 3
        assert stats2["processing"]["events_failed"] == initial_failed  # No new failures
        assert stats2["health"]["is_healthy"]
    
    @pytest.mark.asyncio
    async def test_real_git_commit_tracking(self):
        """Test that git commit hashes are properly tracked"""
        from utils.git_utils import get_current_commit_hash
        
        # Get actual commit hash
        commit_hash = get_current_commit_hash()
        
        # Should be a valid format
        assert len(commit_hash) >= 7  # At least short hash
        assert commit_hash != "current"  # Not the mock value
        
        # If in git repo, should be hex
        if commit_hash not in ["development", "unknown"]:
            try:
                int(commit_hash.replace("-dirty", ""), 16)  # Should be valid hex
            except ValueError:
                pytest.fail(f"Invalid commit hash format: {commit_hash}")


class TestCheckpointRecovery:
    """Test real checkpoint and recovery functionality"""
    
    @pytest.mark.asyncio
    async def test_checkpoint_based_recovery(self, tmp_path):
        """Test recovery from a specific checkpoint"""
        db_path = str(tmp_path / "checkpoint_recovery.db")
        
        # Create consumer and process events
        consumer = IdempotentConsumer(
            consumer_id="checkpoint_recovery",
            consumer_version="1.0.0",
            db_path=db_path,
            checkpoint_interval=5,
            state_class=dict
        )
        
        event_count = {"count": 0}
        
        async def handler(event, state):
            event_count["count"] += 1
            if "total" not in state:
                state["total"] = 0
            state["total"] += 1
            state["last_event"] = event.event_id
            
            # Simulate a crash after 7 events
            if event_count["count"] == 7:
                raise Exception("Simulated crash")
            
            return {"success": True, "new_state": state}
        
        consumer.register_handler("test.event", handler)
        await consumer.initialize()
        
        # Process events until crash
        checkpoint_event_id = None
        for i in range(10):
            event = EventEnvelope(
                event_type="test.event",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={"index": i}
            )
            
            if i == 4:  # This will trigger checkpoint after 5 events
                checkpoint_event_id = event.event_id
            
            try:
                await consumer.process_event(event)
            except Exception as e:
                if "Simulated crash" in str(e):
                    break
                raise
        
        # Verify checkpoint was created
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT * FROM checkpoints ORDER BY created_at DESC LIMIT 1"
            )
            checkpoint = await cursor.fetchone()
            assert checkpoint is not None
            
            # Get checkpoint details
            import json
            # Column 6 is state_data (0=checkpoint_id, 1=consumer_id, 2=event_id, 3=sequence_number, 4=timestamp, 5=state_commit_hash, 6=state_data)
            checkpoint_state = json.loads(checkpoint[6])  # state_data column
            assert checkpoint_state["total"] == 5
        
        # Create new consumer (simulating recovery)
        consumer2 = IdempotentConsumer(
            consumer_id="checkpoint_recovery",
            consumer_version="1.0.0",
            db_path=db_path,
            state_class=dict
        )
        
        # Reset handler without crash
        async def safe_handler(event, state):
            if "total" not in state:
                state["total"] = 0
            state["total"] += 1
            state["last_event"] = event.event_id
            return {"success": True, "new_state": state}
        
        consumer2.register_handler("test.event", safe_handler)
        await consumer2.initialize()
        
        # Should have recovered state
        recovered_state = await consumer2.get_state()
        assert recovered_state["total"] >= 5  # At least checkpoint state
        
        # Process remaining events
        for i in range(7, 10):  # Continue from where we crashed
            event = EventEnvelope(
                event_type="test.event",
                source_service="test",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={"index": i}
            )
            await consumer2.process_event(event)
        
        final_state = await consumer2.get_state()
        # Some events might have been processed before crash
        assert final_state["total"] >= 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])