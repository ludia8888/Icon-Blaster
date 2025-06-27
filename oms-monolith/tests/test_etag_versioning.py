"""
Tests for ETag and Version Tracking functionality
"""
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from typing import Dict, Any

from models.etag import (
    VersionInfo, ResourceVersion, DeltaRequest, DeltaResponse,
    calculate_content_hash, generate_commit_hash, create_json_patch
)
from core.versioning.version_service import VersionTrackingService
from core.auth import UserContext


class TestETagModels:
    """Test ETag model functionality"""
    
    def test_calculate_content_hash(self):
        """Test content hash calculation"""
        content1 = {"name": "test", "value": 123}
        content2 = {"value": 123, "name": "test"}  # Different order
        content3 = {"name": "test", "value": 456}  # Different value
        
        hash1 = calculate_content_hash(content1)
        hash2 = calculate_content_hash(content2)
        hash3 = calculate_content_hash(content3)
        
        # Same content with different order should have same hash
        assert hash1 == hash2
        # Different content should have different hash
        assert hash1 != hash3
        # Hash should be hex string
        assert all(c in '0123456789abcdef' for c in hash1)
    
    def test_generate_commit_hash(self):
        """Test commit hash generation"""
        content_hash = "abc123"
        author = "testuser"
        timestamp = datetime.now(timezone.utc)
        
        # First commit (no parent)
        hash1 = generate_commit_hash(None, content_hash, author, timestamp)
        
        # Second commit (with parent)
        hash2 = generate_commit_hash(hash1, content_hash, author, timestamp)
        
        assert hash1 != hash2  # Different commits
        assert len(hash1) == 64  # SHA256 hex length
        assert len(hash2) == 64
    
    def test_create_json_patch(self):
        """Test JSON patch creation"""
        old_content = {
            "name": "test",
            "value": 123,
            "tags": ["a", "b"]
        }
        
        new_content = {
            "name": "test_updated",
            "value": 123,
            "tags": ["a", "b", "c"],
            "new_field": "added"
        }
        
        patches = create_json_patch(old_content, new_content)
        
        # Check patch operations
        ops = [p["op"] for p in patches]
        assert "replace" in ops  # name changed
        assert "add" in ops  # new_field added
        
        # Find specific patches
        name_patch = next(p for p in patches if p["path"] == "/name")
        assert name_patch["op"] == "replace"
        assert name_patch["value"] == "test_updated"
        
        new_field_patch = next(p for p in patches if p["path"] == "/new_field")
        assert new_field_patch["op"] == "add"
        assert new_field_patch["value"] == "added"
    
    def test_resource_version_etag_generation(self):
        """Test ETag generation from version info"""
        version_info = VersionInfo(
            version=5,
            commit_hash="abcdef123456789012345678901234567890123456789012",
            etag='W/"abcdef123456-5"',
            last_modified=datetime.now(timezone.utc),
            modified_by="testuser",
            change_type="update"
        )
        
        resource_version = ResourceVersion(
            resource_type="object_type",
            resource_id="test123",
            branch="main",
            current_version=version_info,
            content_hash="xyz789",
            content_size=1024
        )
        
        etag = resource_version.generate_etag()
        assert etag == 'W/"abcdef123456-5"'
        assert etag.startswith('W/"')  # Weak ETag
        assert "-5" in etag  # Contains version


class TestVersionTrackingService:
    """Test version tracking service"""
    
    @pytest_asyncio.fixture
    async def version_service(self, tmp_path):
        """Create version service for testing"""
        service = VersionTrackingService(
            db_path=str(tmp_path / "test_versions.db")
        )
        await service.initialize()
        return service
    
    @pytest.fixture
    def test_user(self):
        """Create test user"""
        return UserContext(
            user_id="test123",
            username="testuser",
            email="test@example.com",
            roles=["developer"],
            permissions=[],
            is_admin=False,
            is_service_account=False
        )
    
    @pytest.mark.asyncio
    async def test_track_first_change(self, version_service, test_user):
        """Test tracking the first version of a resource"""
        content = {
            "name": "TestObject",
            "description": "Test description",
            "fields": ["field1", "field2"]
        }
        
        version = await version_service.track_change(
            resource_type="object_type",
            resource_id="obj123",
            branch="main",
            content=content,
            change_type="create",
            user=test_user,
            change_summary="Initial creation"
        )
        
        assert version.current_version.version == 1
        assert version.current_version.parent_version is None
        assert version.current_version.change_type == "create"
        assert version.current_version.modified_by == "testuser"
        assert version.content_size > 0
        assert version.current_version.etag.startswith('W/"')
    
    @pytest.mark.asyncio
    async def test_track_update_change(self, version_service, test_user):
        """Test tracking updates to a resource"""
        # Create initial version
        content_v1 = {"name": "Test", "value": 1}
        await version_service.track_change(
            resource_type="object_type",
            resource_id="obj456",
            branch="main",
            content=content_v1,
            change_type="create",
            user=test_user
        )
        
        # Update resource
        content_v2 = {"name": "Test Updated", "value": 2}
        version = await version_service.track_change(
            resource_type="object_type",
            resource_id="obj456",
            branch="main",
            content=content_v2,
            change_type="update",
            user=test_user,
            fields_changed=["name", "value"]
        )
        
        assert version.current_version.version == 2
        assert version.current_version.parent_version == 1
        assert version.current_version.parent_commit is not None
        assert version.current_version.fields_changed == ["name", "value"]
    
    @pytest.mark.asyncio
    async def test_no_change_tracking(self, version_service, test_user):
        """Test that identical content doesn't create new version"""
        content = {"name": "Test", "value": 123}
        
        # Create initial version
        v1 = await version_service.track_change(
            resource_type="object_type",
            resource_id="obj789",
            branch="main",
            content=content,
            change_type="create",
            user=test_user
        )
        
        # Try to update with same content
        v2 = await version_service.track_change(
            resource_type="object_type",
            resource_id="obj789",
            branch="main",
            content=content,  # Same content
            change_type="update",
            user=test_user
        )
        
        # Should return existing version
        assert v2.current_version.version == v1.current_version.version
        assert v2.current_version.commit_hash == v1.current_version.commit_hash
    
    @pytest.mark.asyncio
    async def test_get_resource_version(self, version_service, test_user):
        """Test retrieving resource version"""
        # Create a version
        content = {"test": "data"}
        await version_service.track_change(
            resource_type="test_type",
            resource_id="test123",
            branch="feature",
            content=content,
            change_type="create",
            user=test_user
        )
        
        # Get latest version
        version = await version_service.get_resource_version(
            "test_type", "test123", "feature"
        )
        
        assert version is not None
        assert version.resource_type == "test_type"
        assert version.resource_id == "test123"
        assert version.branch == "feature"
        assert version.current_version.version == 1
        
        # Get non-existent resource
        missing = await version_service.get_resource_version(
            "test_type", "missing", "feature"
        )
        assert missing is None
    
    @pytest.mark.asyncio
    async def test_validate_etag(self, version_service, test_user):
        """Test ETag validation"""
        # Create a version
        content = {"data": "test"}
        version = await version_service.track_change(
            resource_type="test_type",
            resource_id="etag123",
            branch="main",
            content=content,
            change_type="create",
            user=test_user
        )
        
        etag = version.current_version.etag
        
        # Validate correct ETag
        is_valid, current = await version_service.validate_etag(
            "test_type", "etag123", "main", etag
        )
        assert is_valid == True
        assert current.current_version.etag == etag
        
        # Validate incorrect ETag
        is_valid, current = await version_service.validate_etag(
            "test_type", "etag123", "main", 'W/"wrong-etag"'
        )
        assert is_valid == False
        assert current.current_version.etag == etag
    
    @pytest.mark.asyncio
    async def test_get_delta_no_change(self, version_service, test_user):
        """Test delta request when client is up to date"""
        # Create a version
        content = {"value": 42}
        version = await version_service.track_change(
            resource_type="test_type",
            resource_id="delta123",
            branch="main",
            content=content,
            change_type="create",
            user=test_user
        )
        
        # Request delta with current ETag
        delta_request = DeltaRequest(
            client_etag=version.current_version.etag,
            client_version=version.current_version.version
        )
        
        delta_response = await version_service.get_delta(
            "test_type", "delta123", "main", delta_request
        )
        
        assert delta_response.response_type == "no_change"
        assert delta_response.total_changes == 0
        assert len(delta_response.changes) == 0
    
    @pytest.mark.asyncio
    async def test_get_delta_with_changes(self, version_service, test_user):
        """Test delta request with changes"""
        # Create initial version
        content_v1 = {"name": "Original", "value": 1}
        v1 = await version_service.track_change(
            resource_type="test_type",
            resource_id="delta456",
            branch="main",
            content=content_v1,
            change_type="create",
            user=test_user
        )
        
        # Create update
        content_v2 = {"name": "Updated", "value": 2, "new_field": "added"}
        v2 = await version_service.track_change(
            resource_type="test_type",
            resource_id="delta456",
            branch="main",
            content=content_v2,
            change_type="update",
            user=test_user
        )
        
        # Request delta from v1
        delta_request = DeltaRequest(
            client_version=v1.current_version.version,
            include_full=False
        )
        
        delta_response = await version_service.get_delta(
            "test_type", "delta456", "main", delta_request
        )
        
        assert delta_response.response_type in ["delta", "full"]
        assert delta_response.total_changes == 1
        assert len(delta_response.changes) == 1
        
        change = delta_response.changes[0]
        assert change.from_version == 1
        assert change.to_version == 2
        assert change.operation == "update"
    
    @pytest.mark.asyncio
    async def test_cache_validation(self, version_service, test_user):
        """Test bulk cache validation"""
        # Create some resources
        resources = {
            "res1": {"data": 1},
            "res2": {"data": 2},
            "res3": {"data": 3}
        }
        
        versions = {}
        for res_id, content in resources.items():
            version = await version_service.track_change(
                resource_type="test_type",
                resource_id=res_id,
                branch="main",
                content=content,
                change_type="create",
                user=test_user
            )
            versions[f"test_type:{res_id}"] = version.current_version.etag
        
        # Update one resource
        await version_service.track_change(
            resource_type="test_type",
            resource_id="res2",
            branch="main",
            content={"data": 2, "updated": True},
            change_type="update",
            user=test_user
        )
        
        # Validate cache
        from models.etag import CacheValidation
        validation = CacheValidation(resource_etags=versions)
        
        result = await version_service.validate_cache("main", validation)
        
        assert "test_type:res1" in result.valid_resources
        assert "test_type:res2" in result.stale_resources
        assert "test_type:res3" in result.valid_resources
        assert len(result.deleted_resources) == 0
    
    @pytest.mark.asyncio
    async def test_branch_version_summary(self, version_service, test_user):
        """Test getting branch version summary"""
        # Create resources on different branches
        branches = ["main", "feature", "main"]
        types = ["object_type", "link_type", "object_type"]
        
        for i, (branch, res_type) in enumerate(zip(branches, types)):
            await version_service.track_change(
                resource_type=res_type,
                resource_id=f"res{i}",
                branch=branch,
                content={"index": i},
                change_type="create",
                user=test_user
            )
        
        # Get summary for main branch
        summary = await version_service.get_branch_version_summary("main")
        
        assert summary["branch"] == "main"
        assert "object_type" in summary["resource_types"]
        assert summary["resource_types"]["object_type"]["count"] == 2
        assert summary["total_resources"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])