"""
Integration tests for Time Travel Queries
"""
import pytest
from datetime import datetime, timedelta
import asyncio
from typing import Dict, Any

from core.time_travel import (
    TemporalOperator, TemporalReference, TemporalQuery,
    TemporalResourceQuery, TemporalComparisonQuery,
    TimeTravelQueryService
)
from core.versioning.version_service import VersionTrackingService
from core.auth import UserContext
from models.etag import ResourceVersion


@pytest.fixture
async def version_service():
    """Create version tracking service"""
    service = VersionTrackingService(db_path="./test_data")
    await service.initialize()
    yield service
    # Cleanup
    import os
    import shutil
    if os.path.exists("./test_data"):
        shutil.rmtree("./test_data")


@pytest.fixture
async def time_travel_service(version_service):
    """Create time travel service"""
    service = TimeTravelQueryService(version_service)
    await service.initialize()
    return service


@pytest.fixture
async def sample_data(version_service):
    """Create sample version history"""
    user = UserContext(username="test_user", user_id="123")
    
    # Create initial version
    content_v1 = {
        "name": "TestObject",
        "type": "object_type",
        "fields": ["field1", "field2"]
    }
    
    await version_service.track_change(
        resource_type="object_type",
        resource_id="test_obj_1",
        branch="main",
        content=content_v1,
        change_type="create",
        user=user,
        change_summary="Initial creation"
    )
    
    # Wait to ensure different timestamps
    await asyncio.sleep(0.1)
    
    # Update version
    content_v2 = {
        "name": "TestObject",
        "type": "object_type",
        "fields": ["field1", "field2", "field3"],
        "description": "Updated object"
    }
    
    await version_service.track_change(
        resource_type="object_type",
        resource_id="test_obj_1",
        branch="main",
        content=content_v2,
        change_type="update",
        user=user,
        change_summary="Added field3 and description",
        fields_changed=["fields", "description"]
    )
    
    # Create another object
    content_obj2 = {
        "name": "TestObject2",
        "type": "object_type",
        "fields": ["fieldA"]
    }
    
    await version_service.track_change(
        resource_type="object_type",
        resource_id="test_obj_2",
        branch="main",
        content=content_obj2,
        change_type="create",
        user=user
    )
    
    return {
        "timestamps": {
            "before_all": datetime.utcnow() - timedelta(hours=1),
            "after_v1": datetime.utcnow() - timedelta(minutes=30),
            "after_v2": datetime.utcnow() - timedelta(minutes=15),
            "current": datetime.utcnow()
        }
    }


class TestAsOfQueries:
    """Test AS OF temporal queries"""
    
    @pytest.mark.asyncio
    async def test_as_of_timestamp(self, time_travel_service, sample_data):
        """Test querying as of specific timestamp"""
        # Query as of time after first version
        query = TemporalResourceQuery(
            resource_type="object_type",
            resource_id="test_obj_1",
            branch="main",
            temporal=TemporalQuery(
                operator=TemporalOperator.AS_OF,
                point_in_time=TemporalReference(
                    timestamp=sample_data["timestamps"]["after_v1"]
                )
            )
        )
        
        result = await time_travel_service.query_as_of(query)
        
        assert len(result.resources) == 1
        assert result.resources[0].version == 1
        assert result.resources[0].content["fields"] == ["field1", "field2"]
        assert "description" not in result.resources[0].content
    
    @pytest.mark.asyncio
    async def test_as_of_relative_time(self, time_travel_service, sample_data):
        """Test querying with relative time"""
        # Query as of 1 hour ago (before any data)
        query = TemporalResourceQuery(
            resource_type="object_type",
            branch="main",
            temporal=TemporalQuery(
                operator=TemporalOperator.AS_OF,
                point_in_time=TemporalReference(relative_time="-2h")
            )
        )
        
        result = await time_travel_service.query_as_of(query)
        
        assert len(result.resources) == 0
        assert result.total_count == 0
    
    @pytest.mark.asyncio
    async def test_as_of_version(self, time_travel_service, sample_data):
        """Test querying specific version"""
        # This would require version-based query implementation
        # For now, test with timestamp
        query = TemporalResourceQuery(
            resource_type="object_type",
            resource_id="test_obj_1",
            branch="main",
            temporal=TemporalQuery(
                operator=TemporalOperator.AS_OF,
                point_in_time=TemporalReference(
                    timestamp=datetime.utcnow()
                )
            )
        )
        
        result = await time_travel_service.query_as_of(query)
        
        assert len(result.resources) == 1
        assert result.resources[0].version == 2
        assert "description" in result.resources[0].content


class TestBetweenQueries:
    """Test BETWEEN temporal queries"""
    
    @pytest.mark.asyncio
    async def test_between_timestamps(self, time_travel_service, sample_data):
        """Test querying between timestamps"""
        query = TemporalResourceQuery(
            resource_type="object_type",
            resource_id="test_obj_1",
            branch="main",
            temporal=TemporalQuery(
                operator=TemporalOperator.BETWEEN,
                start_time=TemporalReference(
                    timestamp=sample_data["timestamps"]["before_all"]
                ),
                end_time=TemporalReference(
                    timestamp=sample_data["timestamps"]["current"]
                )
            )
        )
        
        result = await time_travel_service.query_between(query)
        
        assert len(result.resources) == 2  # Both versions
        assert result.resources[0].version == 1
        assert result.resources[1].version == 2
        assert result.versions_scanned == 2
    
    @pytest.mark.asyncio
    async def test_between_all_resources(self, time_travel_service, sample_data):
        """Test querying all resources between times"""
        query = TemporalResourceQuery(
            resource_type="object_type",
            branch="main",
            temporal=TemporalQuery(
                operator=TemporalOperator.BETWEEN,
                start_time=TemporalReference(
                    timestamp=sample_data["timestamps"]["after_v1"]
                ),
                end_time=TemporalReference(
                    timestamp=sample_data["timestamps"]["current"]
                )
            )
        )
        
        result = await time_travel_service.query_between(query)
        
        # Should get v2 of obj1 and v1 of obj2
        assert len(result.resources) >= 2
        resource_ids = {r.resource_id for r in result.resources}
        assert "test_obj_1" in resource_ids
        assert "test_obj_2" in resource_ids


class TestAllVersionsQuery:
    """Test ALL_VERSIONS queries"""
    
    @pytest.mark.asyncio
    async def test_all_versions(self, time_travel_service, sample_data):
        """Test getting all versions of a resource"""
        query = TemporalResourceQuery(
            resource_type="object_type",
            resource_id="test_obj_1",
            branch="main",
            temporal=TemporalQuery(
                operator=TemporalOperator.ALL_VERSIONS
            )
        )
        
        result = await time_travel_service.query_all_versions(query)
        
        assert len(result.resources) == 2
        assert result.resources[0].version == 1
        assert result.resources[1].version == 2
        
        # Check version linkage
        assert result.resources[0].next_version == 2
        assert result.resources[1].previous_version == 1
        
        # Check duration calculation
        assert result.resources[0].version_duration is not None
        assert result.resources[0].version_duration > 0


class TestTemporalComparison:
    """Test temporal state comparison"""
    
    @pytest.mark.asyncio
    async def test_compare_states(self, time_travel_service, sample_data):
        """Test comparing states at different times"""
        query = TemporalComparisonQuery(
            resource_types=["object_type"],
            branch="main",
            time1=TemporalReference(
                timestamp=sample_data["timestamps"]["after_v1"]
            ),
            time2=TemporalReference(
                timestamp=sample_data["timestamps"]["current"]
            ),
            detailed_diff=True
        )
        
        result = await time_travel_service.compare_temporal_states(query)
        
        assert result.total_created == 1  # test_obj_2
        assert result.total_updated == 1  # test_obj_1
        assert result.total_deleted == 0
        
        # Check differences
        obj_type_diffs = result.differences["object_type"]
        
        # Find the update diff
        update_diff = next(d for d in obj_type_diffs if d.operation == "updated")
        assert update_diff.resource_id == "test_obj_1"
        assert update_diff.fields_added == 1  # description
        assert update_diff.fields_modified == 1  # fields
        
        # Find the create diff
        create_diff = next(d for d in obj_type_diffs if d.operation == "created")
        assert create_diff.resource_id == "test_obj_2"


class TestResourceTimeline:
    """Test resource timeline generation"""
    
    @pytest.mark.asyncio
    async def test_timeline(self, time_travel_service, sample_data):
        """Test getting resource timeline"""
        timeline = await time_travel_service.get_resource_timeline(
            "object_type", "test_obj_1", "main"
        )
        
        assert timeline.total_versions == 2
        assert timeline.total_updates == 1
        assert len(timeline.events) == 2
        
        assert timeline.events[0].event_type == "create"
        assert timeline.events[1].event_type == "update"
        assert timeline.events[1].fields_changed == ["fields", "description"]
        
        assert timeline.unique_contributors == ["test_user"]
        assert timeline.average_time_between_changes is not None


class TestTemporalSnapshot:
    """Test temporal snapshot creation"""
    
    @pytest.mark.asyncio
    async def test_create_snapshot(self, time_travel_service, sample_data):
        """Test creating system snapshot"""
        snapshot = await time_travel_service.create_temporal_snapshot(
            branch="main",
            timestamp=sample_data["timestamps"]["current"],
            created_by="test_user",
            description="Test snapshot",
            include_data=True
        )
        
        assert snapshot.total_resources == 2
        assert snapshot.resource_counts["object_type"] == 2
        assert snapshot.resources is not None
        assert len(snapshot.resources["object_type"]) == 2
        
        # Verify snapshot data
        obj_names = {obj["name"] for obj in snapshot.resources["object_type"]}
        assert "TestObject" in obj_names
        assert "TestObject2" in obj_names


class TestEdgeCases:
    """Test edge cases and error handling"""
    
    @pytest.mark.asyncio
    async def test_query_deleted_resources(self, time_travel_service, version_service):
        """Test querying deleted resources"""
        user = UserContext(username="test_user", user_id="123")
        
        # Create and then delete a resource
        await version_service.track_change(
            resource_type="object_type",
            resource_id="deleted_obj",
            branch="main",
            content={"name": "ToBeDeleted"},
            change_type="create",
            user=user
        )
        
        await asyncio.sleep(0.1)
        
        await version_service.track_change(
            resource_type="object_type",
            resource_id="deleted_obj",
            branch="main",
            content={},
            change_type="delete",
            user=user
        )
        
        # Query without include_deleted
        query = TemporalResourceQuery(
            resource_type="object_type",
            branch="main",
            temporal=TemporalQuery(
                operator=TemporalOperator.AS_OF,
                point_in_time=TemporalReference(timestamp=datetime.utcnow()),
                include_deleted=False
            )
        )
        
        result = await time_travel_service.query_as_of(query)
        deleted_found = any(r.resource_id == "deleted_obj" for r in result.resources)
        assert not deleted_found
        
        # Query with include_deleted
        query.temporal.include_deleted = True
        result = await time_travel_service.query_as_of(query)
        deleted_found = any(r.resource_id == "deleted_obj" for r in result.resources)
        assert deleted_found
    
    @pytest.mark.asyncio
    async def test_invalid_temporal_reference(self, time_travel_service):
        """Test invalid temporal reference"""
        with pytest.raises(ValueError):
            ref = TemporalReference(relative_time="invalid")
            ref.to_timestamp()
    
    @pytest.mark.asyncio
    async def test_empty_time_range(self, time_travel_service):
        """Test querying empty time range"""
        future_time = datetime.utcnow() + timedelta(days=1)
        
        query = TemporalResourceQuery(
            resource_type="object_type",
            branch="main",
            temporal=TemporalQuery(
                operator=TemporalOperator.BETWEEN,
                start_time=TemporalReference(timestamp=future_time),
                end_time=TemporalReference(timestamp=future_time + timedelta(hours=1))
            )
        )
        
        result = await time_travel_service.query_between(query)
        assert len(result.resources) == 0
        assert result.total_count == 0