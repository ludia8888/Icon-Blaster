"""
Integration tests for Schema Generation API endpoints

Tests Phase 5 requirements: GraphQL and OpenAPI generation endpoints
"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from main_enterprise import app, services
from models.domain import (
    ObjectType, LinkType, Property, 
    Cardinality, Directionality, Status, Visibility
)


@pytest.fixture
async def async_client():
    """Create async test client"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
def mock_auth():
    """Mock authentication"""
    with patch("middleware.auth_middleware.get_current_user") as mock:
        mock.return_value = AsyncMock(return_value="test_user")
        yield mock


@pytest.fixture
def sample_object_types():
    """Create sample object types for testing"""
    return [
        ObjectType(
            id="User",
            name="User",
            display_name="User",
            status=Status.ACTIVE,
            properties=[
                Property(
                    id="user_name",
                    object_type_id="User",
                    name="name",
                    display_name="Name",
                    data_type_id="string",
                    is_required=True,
                    visibility=Visibility.VISIBLE,
                    version_hash="test",
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow()
                ),
                Property(
                    id="user_email",
                    object_type_id="User",
                    name="email",
                    display_name="Email",
                    data_type_id="string",
                    is_required=True,
                    visibility=Visibility.VISIBLE,
                    version_hash="test",
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow()
                )
            ],
            version_hash="test_hash",
            created_by="test_user",
            created_at=datetime.utcnow(),
            modified_by="test_user",
            modified_at=datetime.utcnow()
        ),
        ObjectType(
            id="Post",
            name="Post",
            display_name="Post",
            status=Status.ACTIVE,
            properties=[
                Property(
                    id="post_title",
                    object_type_id="Post",
                    name="title",
                    display_name="Title",
                    data_type_id="string",
                    is_required=True,
                    visibility=Visibility.VISIBLE,
                    version_hash="test",
                    created_at=datetime.utcnow(),
                    modified_at=datetime.utcnow()
                )
            ],
            version_hash="test_hash",
            created_by="test_user",
            created_at=datetime.utcnow(),
            modified_by="test_user",
            modified_at=datetime.utcnow()
        )
    ]


@pytest.fixture
def sample_link_types():
    """Create sample link types for testing"""
    return [
        LinkType(
            id="user_posts",
            name="posts",
            displayName="Posts",
            fromTypeId="User",
            toTypeId="Post",
            cardinality=Cardinality.ONE_TO_MANY,
            directionality=Directionality.UNIDIRECTIONAL,
            cascadeDelete=False,
            isRequired=False,
            status=Status.ACTIVE,
            versionHash="test_hash",
            createdBy="test_user",
            createdAt=datetime.utcnow(),
            modifiedBy="test_user",
            modifiedAt=datetime.utcnow()
        )
    ]


class TestGraphQLSchemaGeneration:
    """Test GraphQL schema generation endpoints"""
    
    @pytest.mark.asyncio
    async def test_generate_graphql_schema_all_types(
        self, 
        async_client: AsyncClient,
        mock_auth,
        sample_object_types,
        sample_link_types
    ):
        """Test generating GraphQL schema for all active types"""
        # Mock schema registry
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.list_object_types = AsyncMock(return_value=sample_object_types)
            mock_registry.list_link_types = AsyncMock(return_value=sample_link_types)
            
            response = await async_client.post(
                "/api/v1/schema-generation/graphql",
                json={
                    "include_inactive": False,
                    "export_metadata": True
                },
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["format"] == "graphql"
            assert "type User {" in data["schema"]
            assert "type Post {" in data["schema"]
            assert "posts: [Post!]" in data["schema"]  # Link field
            assert data["object_types_included"] == ["User", "Post"]
            assert data["link_types_included"] == ["user_posts"]
            assert data["metadata"] is not None
    
    @pytest.mark.asyncio
    async def test_generate_graphql_schema_specific_types(
        self,
        async_client: AsyncClient,
        mock_auth,
        sample_object_types,
        sample_link_types
    ):
        """Test generating GraphQL schema for specific types"""
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.get_object_type = AsyncMock(
                side_effect=lambda id: next((t for t in sample_object_types if t.id == id), None)
            )
            mock_registry.list_link_types = AsyncMock(return_value=sample_link_types)
            
            response = await async_client.post(
                "/api/v1/schema-generation/graphql",
                json={
                    "object_type_ids": ["User"],
                    "export_metadata": False
                },
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert "type User {" in data["schema"]
            assert "type Post {" not in data["schema"]  # Not included
            assert data["object_types_included"] == ["User"]
            assert data["metadata"] is None  # Metadata not requested
    
    @pytest.mark.asyncio
    async def test_generate_graphql_schema_type_not_found(
        self,
        async_client: AsyncClient,
        mock_auth
    ):
        """Test error when object type not found"""
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.get_object_type = AsyncMock(return_value=None)
            
            response = await async_client.post(
                "/api/v1/schema-generation/graphql",
                json={
                    "object_type_ids": ["NonExistent"]
                },
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"]


class TestOpenAPISchemaGeneration:
    """Test OpenAPI schema generation endpoints"""
    
    @pytest.mark.asyncio
    async def test_generate_openapi_schema(
        self,
        async_client: AsyncClient,
        mock_auth,
        sample_object_types,
        sample_link_types
    ):
        """Test generating OpenAPI schema"""
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.list_object_types = AsyncMock(return_value=sample_object_types)
            mock_registry.list_link_types = AsyncMock(return_value=sample_link_types)
            
            response = await async_client.post(
                "/api/v1/schema-generation/openapi",
                json={
                    "api_info": {
                        "title": "Test API",
                        "version": "1.0.0",
                        "description": "Test description"
                    }
                },
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["format"] == "openapi"
            
            # Parse the schema JSON
            import json
            spec = json.loads(data["schema"])
            
            assert spec["openapi"] == "3.0.3"
            assert spec["info"]["title"] == "Test API"
            assert "User" in spec["components"]["schemas"]
            assert "Post" in spec["components"]["schemas"]
            assert "/users" in spec["paths"]
            assert "/posts" in spec["paths"]
    
    @pytest.mark.asyncio
    async def test_generate_openapi_with_hal_links(
        self,
        async_client: AsyncClient,
        mock_auth,
        sample_object_types,
        sample_link_types
    ):
        """Test that OpenAPI includes HAL-style links"""
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.list_object_types = AsyncMock(return_value=sample_object_types)
            mock_registry.list_link_types = AsyncMock(return_value=sample_link_types)
            
            response = await async_client.post(
                "/api/v1/schema-generation/openapi",
                json={},
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            import json
            spec = json.loads(data["schema"])
            
            # Check User schema has _links
            user_schema = spec["components"]["schemas"]["User"]
            assert "_links" in user_schema["properties"]
            assert "_embedded" in user_schema["properties"]
            
            # Check link endpoints
            assert "/users/{id}/posts" in spec["paths"]


class TestLinkMetadata:
    """Test link metadata endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_link_metadata(
        self,
        async_client: AsyncClient,
        mock_auth,
        sample_object_types,
        sample_link_types
    ):
        """Test getting link metadata for an object type"""
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.get_object_type = AsyncMock(return_value=sample_object_types[0])
            mock_registry.list_link_types = AsyncMock(return_value=sample_link_types)
            
            response = await async_client.get(
                "/api/v1/schema-generation/link-metadata/User",
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["object_type_id"] == "User"
            assert data["object_type_name"] == "User"
            assert len(data["link_fields"]) > 0
            
            # Check link field details
            link_field = data["link_fields"][0]
            assert link_field["field_name"] == "posts"
            assert link_field["field_type"] == "LinkSet"
            assert link_field["target_type"] == "Post"
    
    @pytest.mark.asyncio
    async def test_get_link_metadata_type_not_found(
        self,
        async_client: AsyncClient,
        mock_auth
    ):
        """Test error when object type not found"""
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.get_object_type = AsyncMock(return_value=None)
            
            response = await async_client.get(
                "/api/v1/schema-generation/link-metadata/NonExistent",
                headers={"Authorization": "Bearer test_token"}
            )
            
            assert response.status_code == 404


class TestSchemaExport:
    """Test schema export endpoints"""
    
    @pytest.mark.asyncio
    async def test_export_graphql_schema(
        self,
        async_client: AsyncClient,
        mock_auth,
        sample_object_types,
        sample_link_types
    ):
        """Test exporting GraphQL schema to file"""
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.list_object_types = AsyncMock(return_value=sample_object_types)
            mock_registry.list_link_types = AsyncMock(return_value=sample_link_types)
            
            # Mock file operations
            import builtins
            with patch("builtins.open", create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file
                
                with patch("os.makedirs") as mock_makedirs:
                    response = await async_client.post(
                        "/api/v1/schema-generation/export/graphql",
                        params={"filename": "test_schema.graphql"},
                        headers={"Authorization": "Bearer test_token"}
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    
                    assert data["filename"] == "test_schema.graphql"
                    assert data["format"] == "graphql"
                    assert data["content_type"] == "text/plain"
                    assert "path" in data
                    
                    # Check file write was called
                    mock_makedirs.assert_called_once()
                    mock_file.write.assert_called()
    
    @pytest.mark.asyncio
    async def test_export_openapi_schema(
        self,
        async_client: AsyncClient,
        mock_auth,
        sample_object_types,
        sample_link_types
    ):
        """Test exporting OpenAPI schema to file"""
        with patch("core.schema.registry.schema_registry") as mock_registry:
            mock_registry.list_object_types = AsyncMock(return_value=sample_object_types)
            mock_registry.list_link_types = AsyncMock(return_value=sample_link_types)
            
            import builtins
            with patch("builtins.open", create=True) as mock_open:
                mock_file = MagicMock()
                mock_open.return_value.__enter__.return_value = mock_file
                
                with patch("os.makedirs") as mock_makedirs:
                    response = await async_client.post(
                        "/api/v1/schema-generation/export/openapi",
                        headers={"Authorization": "Bearer test_token"}
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    
                    assert data["format"] == "openapi"
                    assert data["content_type"] == "application/json"
                    assert data["filename"].endswith(".json")
                    
                    mock_file.write.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])