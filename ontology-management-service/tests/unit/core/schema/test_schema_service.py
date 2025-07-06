"""Unit tests for SchemaService - Core ontology management functionality."""

import pytest
import asyncio
import sys
import os
import json
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, List, Optional

# Add the project root to the path to import modules directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))

# Mock external dependencies before imports
sys.modules['prometheus_client'] = MagicMock()
sys.modules['common_logging'] = MagicMock()
sys.modules['common_logging.setup'] = MagicMock()

# Import modules directly using importlib to avoid dependency issues
import importlib.util

# Load SchemaService
schema_service_spec = importlib.util.spec_from_file_location(
    "schema_service",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "core", "schema", "service.py")
)
schema_service_module = importlib.util.module_from_spec(schema_service_spec)
sys.modules['schema_service'] = schema_service_module

# Mock all the dependencies before loading
sys.modules['database.clients.terminus_db'] = MagicMock()
sys.modules['models.domain'] = MagicMock()
sys.modules['shared.terminus_context'] = MagicMock()

try:
    schema_service_spec.loader.exec_module(schema_service_module)
except Exception as e:
    print(f"Warning: Could not load SchemaService module: {e}")

# Import what we need
SchemaService = getattr(schema_service_module, 'SchemaService', None)

# Create mock classes if imports fail
if SchemaService is None:
    class SchemaService:
        def __init__(self, *args, **kwargs):
            pass

# Mock data classes
class ObjectTypeCreate:
    def __init__(self, **kwargs):
        self.name = kwargs.get('name', 'TestType')
        self.display_name = kwargs.get('display_name', 'Test Type')
        self.description = kwargs.get('description', 'Test description')
        for key, value in kwargs.items():
            setattr(self, key, value)

class ObjectType:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestSchemaServiceInitialization:
    """Test suite for SchemaService initialization and basic setup."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tdb_endpoint = "http://test-terminus.local"
        self.mock_event_publisher = Mock()
        
        with patch('core.schema.service.TerminusDBClient') as mock_tdb_client:
            self.mock_tdb = Mock()
            mock_tdb_client.return_value = self.mock_tdb
            
            self.service = SchemaService(
                tdb_endpoint=self.tdb_endpoint,
                event_publisher=self.mock_event_publisher
            )
    
    def test_schema_service_initialization(self):
        """Test SchemaService initialization with dependencies."""
        assert self.service.tdb_endpoint == self.tdb_endpoint
        assert self.service.event_publisher == self.mock_event_publisher
        assert self.service.db_name == os.getenv("TERMINUSDB_DB", "oms")
        assert self.service.tdb is None  # Not initialized yet
    
    def test_schema_service_default_endpoint(self):
        """Test SchemaService initialization with default endpoint."""
        with patch('core.schema.service.TerminusDBClient'):
            service = SchemaService()
            assert service.tdb_endpoint == "http://localhost:6363"
            assert service.event_publisher is None
    
    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful service initialization."""
        # Mock the TerminusDBClient constructor and methods
        with patch('schema_service.TerminusDBClient') as mock_tdb_client:
            mock_tdb_instance = AsyncMock()
            mock_tdb_instance.connect = AsyncMock()
            mock_tdb_client.return_value = mock_tdb_instance
            
            await self.service.initialize()
            
            # Verify TerminusDBClient was created with correct parameters
            mock_tdb_client.assert_called_once_with(
                endpoint=self.tdb_endpoint,
                username="admin",
                password="changeme-admin-pass",
                service_name="schema-service"
            )
            
            # Verify connection was established
            mock_tdb_instance.connect.assert_called_once()
            assert self.service.tdb == mock_tdb_instance
    
    @pytest.mark.asyncio
    async def test_initialize_connection_failure(self):
        """Test initialization when connection fails."""
        with patch('schema_service.TerminusDBClient') as mock_tdb_client:
            mock_tdb_instance = AsyncMock()
            mock_tdb_instance.connect = AsyncMock(side_effect=Exception("Connection failed"))
            mock_tdb_client.return_value = mock_tdb_instance
            
            # Should not raise exception (failures are logged)
            await self.service.initialize()
            
            # Verify connection was attempted
            mock_tdb_instance.connect.assert_called_once()


class TestSchemaServiceObjectTypeOperations:
    """Test suite for SchemaService ObjectType operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('core.schema.service.TerminusDBClient'):
            self.service = SchemaService(tdb_endpoint="http://test.local")
            
            # Setup mock TDB client
            self.mock_tdb = Mock()
            self.mock_client = Mock()
            self.mock_tdb.client = self.mock_client
            self.mock_tdb.is_connected = Mock(return_value=True)
            self.service.tdb = self.mock_tdb
    
    @pytest.mark.asyncio
    async def test_list_object_types_success(self):
        """Test successful ObjectType listing."""
        # Mock response data
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''{"@type": "ObjectType", "@id": "ObjectType/Person", "name": "Person"}
{"@type": "ObjectType", "@id": "ObjectType/Organization", "name": "Organization"}'''
        
        self.mock_client.get = AsyncMock(return_value=mock_response)
        
        result = await self.service.list_object_types("main")
        
        # Verify API call
        self.mock_client.get.assert_called_once_with(
            f"/api/document/admin/{self.service.db_name}?type=ObjectType",
            auth=("admin", "root")
        )
        
        # Verify result
        assert len(result) == 2
        assert result[0]["name"] == "Person"
        assert result[1]["name"] == "Organization"
    
    @pytest.mark.asyncio
    async def test_list_object_types_empty_response(self):
        """Test ObjectType listing with empty response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = ""
        
        self.mock_client.get = AsyncMock(return_value=mock_response)
        
        result = await self.service.list_object_types()
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_list_object_types_malformed_json(self):
        """Test ObjectType listing with malformed JSON response."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '''{"@type": "ObjectType", "name": "Person"}
{invalid json}
{"@type": "ObjectType", "name": "Organization"}'''
        
        self.mock_client.get = AsyncMock(return_value=mock_response)
        
        result = await self.service.list_object_types()
        
        # Should skip invalid JSON lines and return valid ones
        assert len(result) == 2
        assert result[0]["name"] == "Person"
        assert result[1]["name"] == "Organization"
    
    @pytest.mark.asyncio
    async def test_list_object_types_api_error(self):
        """Test ObjectType listing with API error response."""
        mock_response = Mock()
        mock_response.status_code = 404
        
        self.mock_client.get = AsyncMock(return_value=mock_response)
        
        result = await self.service.list_object_types()
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_list_object_types_connection_error(self):
        """Test ObjectType listing with connection error."""
        self.mock_client.get = AsyncMock(side_effect=Exception("Network error"))
        
        result = await self.service.list_object_types()
        
        assert result == []
    
    @pytest.mark.asyncio
    async def test_list_object_types_not_connected(self):
        """Test ObjectType listing when not connected."""
        self.mock_tdb.is_connected = Mock(return_value=False)
        
        # Mock reinitialize
        with patch.object(self.service, 'initialize', new_callable=AsyncMock) as mock_init:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = '{"@type": "ObjectType", "name": "Person"}'
            self.mock_client.get = AsyncMock(return_value=mock_response)
            
            result = await self.service.list_object_types()
            
            # Should attempt to reconnect
            mock_init.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_object_type_success(self):
        """Test successful ObjectType creation."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json = Mock(return_value={"status": "success"})
        
        self.mock_client.post = AsyncMock(return_value=mock_response)
        
        # Test data
        create_data = ObjectTypeCreate(
            name="TestType",
            display_name="Test Type",
            description="A test type"
        )
        
        result = await self.service.create_object_type("main", create_data)
        
        # Verify API call
        self.mock_client.post.assert_called_once()
        call_args = self.mock_client.post.call_args
        
        assert "/api/document/admin/" in call_args[0][0]
        assert "author=OMS" in call_args[0][0]
        assert call_args.kwargs["auth"] == ("admin", "root")
        
        # Verify document structure
        doc_data = call_args.kwargs["json"][0]
        assert doc_data["@type"] == "ObjectType"
        assert doc_data["@id"] == "ObjectType/TestType"
        assert doc_data["name"] == "TestType"
        assert doc_data["displayName"] == "Test Type"
        assert doc_data["description"] == "A test type"
        
        # Verify result (implementation returns mock ObjectType)
        assert result is not None
    
    @pytest.mark.asyncio
    async def test_create_object_type_with_defaults(self):
        """Test ObjectType creation with default values."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json = Mock(return_value={"status": "success"})
        
        self.mock_client.post = AsyncMock(return_value=mock_response)
        
        # Test data with minimal fields - use proper mock data
        create_data = Mock()
        create_data.name = "MinimalType"
        create_data.display_name = None
        create_data.description = None
        
        result = await self.service.create_object_type("main", create_data)
        
        # Verify document uses defaults
        call_args = self.mock_client.post.call_args
        doc_data = call_args.kwargs["json"][0]
        
        assert doc_data["displayName"] == "MinimalType"  # Defaults to name
        assert doc_data["description"] == ""  # Defaults to empty string
    
    @pytest.mark.asyncio
    async def test_create_object_type_api_error(self):
        """Test ObjectType creation with API error."""
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.json = Mock(return_value={"error": "Invalid data"})
        
        self.mock_client.post = AsyncMock(return_value=mock_response)
        
        create_data = ObjectTypeCreate(name="ErrorType")
        
        with pytest.raises(Exception):
            await self.service.create_object_type("main", create_data)
    
    @pytest.mark.asyncio
    async def test_create_object_type_not_connected(self):
        """Test ObjectType creation when not connected."""
        self.mock_tdb.is_connected = Mock(return_value=False)
        
        # Mock reinitialize
        with patch.object(self.service, 'initialize', new_callable=AsyncMock) as mock_init:
            mock_response = Mock()
            mock_response.status_code = 201
            mock_response.json = Mock(return_value={"status": "success"})
            self.mock_client.post = AsyncMock(return_value=mock_response)
            
            create_data = ObjectTypeCreate(name="TestType")
            result = await self.service.create_object_type("main", create_data)
            
            # Should attempt to reconnect
            mock_init.assert_called_once()


class TestSchemaServiceValidationAndPermissions:
    """Test suite for SchemaService validation and permission checking."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('core.schema.service.TerminusDBClient'):
            self.service = SchemaService()
    
    @pytest.mark.asyncio
    async def test_check_permission_success(self):
        """Test successful permission check."""
        user = {"id": "user123", "permissions": ["schema:write"]}
        
        result = await self.service._check_permission(user, "schema:write", "main")
        
        # Basic implementation - should be True for any valid user
        assert result is True
    
    @pytest.mark.asyncio
    async def test_validate_object_type_success(self):
        """Test successful ObjectType validation."""
        data = ObjectTypeCreate(
            name="ValidType",
            display_name="Valid Type",
            description="A valid type"
        )
        
        result = await self.service._validate_object_type(data)
        
        # Basic validation should return empty dict (no errors)
        assert isinstance(result, dict)


class TestSchemaServiceConnectionManagement:
    """Test suite for SchemaService connection management."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('core.schema.service.TerminusDBClient'):
            self.service = SchemaService()
            
            # Setup mock TDB client
            self.mock_tdb = Mock()
            self.service.tdb = self.mock_tdb
    
    @pytest.mark.asyncio
    async def test_reconnection_on_disconnection(self):
        """Test automatic reconnection when connection is lost."""
        # First call returns False (disconnected), second call returns True
        self.mock_tdb.is_connected = Mock(side_effect=[False, True])
        
        with patch.object(self.service, 'initialize', new_callable=AsyncMock) as mock_init:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = ""
            self.mock_tdb.client.get = AsyncMock(return_value=mock_response)
            
            await self.service.list_object_types()
            
            # Should have attempted to reconnect
            mock_init.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_no_reconnection_when_connected(self):
        """Test no reconnection attempt when already connected."""
        self.mock_tdb.is_connected = Mock(return_value=True)
        
        with patch.object(self.service, 'initialize', new_callable=AsyncMock) as mock_init:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = ""
            self.mock_tdb.client.get = AsyncMock(return_value=mock_response)
            
            await self.service.list_object_types()
            
            # Should not have attempted to reconnect
            mock_init.assert_not_called()


# Test data factories
class SchemaTestDataFactory:
    """Factory for creating test data objects."""
    
    @staticmethod
    def create_object_type_data(
        name: str = "TestType",
        display_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> ObjectTypeCreate:
        """Create ObjectTypeCreate test data."""
        return ObjectTypeCreate(
            name=name,
            display_name=display_name or f"{name} Display",
            description=description or f"Description for {name}"
        )
    
    @staticmethod
    def create_object_type_response(
        name: str = "TestType",
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create NDJSON response for ObjectType query."""
        base_obj = {
            "@type": "ObjectType",
            "@id": f"ObjectType/{name}",
            "name": name,
            "displayName": f"{name} Display",
            "description": f"Description for {name}"
        }
        
        if additional_fields:
            base_obj.update(additional_fields)
        
        return json.dumps(base_obj)
    
    @staticmethod
    def create_multi_object_type_response(names: List[str]) -> str:
        """Create NDJSON response for multiple ObjectTypes."""
        lines = []
        for name in names:
            lines.append(SchemaTestDataFactory.create_object_type_response(name))
        return "\n".join(lines)