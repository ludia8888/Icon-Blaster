"""Fixed unit tests for TerminusDBClient - Data persistence layer functionality."""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, patch, MagicMock, AsyncMock, call
from typing import Dict, Any, Optional, List
import httpx

# Add the project root to the path to import modules directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))

# Mock external dependencies before imports
sys.modules['prometheus_client'] = MagicMock()
sys.modules['common_logging'] = MagicMock()
sys.modules['common_logging.setup'] = MagicMock()
sys.modules['opentelemetry'] = MagicMock()
sys.modules['opentelemetry.trace'] = MagicMock()

# Import modules directly using importlib to avoid dependency issues
import importlib.util

# Load TerminusDBClient
terminus_client_spec = importlib.util.spec_from_file_location(
    "terminus_client",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "database", "clients", "terminus_db.py")
)
terminus_client_module = importlib.util.module_from_spec(terminus_client_spec)
sys.modules['terminus_client'] = terminus_client_module

# Mock all the dependencies before loading
sys.modules['database.clients.unified_http_client'] = MagicMock()
sys.modules['utils.retry_strategy'] = MagicMock()

# Mock the add_span_attributes function that's used in the decorators
def mock_add_span_attributes(attrs):
    pass

# Mock the trace functions and decorators
sys.modules['terminus_client'].add_span_attributes = mock_add_span_attributes

try:
    terminus_client_spec.loader.exec_module(terminus_client_module)
except Exception as e:
    print(f"Warning: Could not load TerminusDBClient module: {e}")

# Import what we need
TerminusDBClient = getattr(terminus_client_module, 'TerminusDBClient', None)

# Create mock classes if imports fail
if TerminusDBClient is None:
    class TerminusDBClient:
        def __init__(self, *args, **kwargs):
            pass


class TestTerminusDBClientInitialization:
    """Test suite for TerminusDBClient initialization and basic setup."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.endpoint = "http://test-terminus.local"
        self.username = "test_user"
        self.password = "test_pass"
        self.service_name = "test_service"
        
        with patch('terminus_client.create_terminus_client'), \
             patch('terminus_client.create_secure_client'):
            
            self.client = TerminusDBClient(
                endpoint=self.endpoint,
                username=self.username,
                password=self.password,
                service_name=self.service_name,
                use_connection_pool=False  # Disable for testing
            )
    
    def test_terminus_client_initialization(self):
        """Test TerminusDBClient initialization with parameters."""
        assert self.client.endpoint == self.endpoint
        assert self.client.username == self.username
        assert self.client.password == self.password
        assert self.client.service_name == self.service_name
        assert self.client.use_connection_pool is False
        assert self.client.client is None  # Not initialized yet
    
    def test_terminus_client_cache_configuration(self):
        """Test TerminusDB internal cache configuration."""
        # Test default cache settings
        assert self.client.cache_size == int(os.getenv("TERMINUSDB_LRU_CACHE_SIZE", "500000000"))
        assert self.client.enable_internal_cache == (os.getenv("TERMINUSDB_CACHE_ENABLED", "true").lower() == "true")


class TestTerminusDBClientConnection:
    """Test suite for TerminusDBClient connection management."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('terminus_client.create_terminus_client'), \
             patch('terminus_client.create_secure_client'):
            
            self.client = TerminusDBClient(endpoint="http://test.local", use_connection_pool=False)
    
    @pytest.mark.asyncio
    async def test_context_manager_enter(self):
        """Test async context manager __aenter__."""
        with patch.object(self.client, '_initialize_client', new_callable=AsyncMock) as mock_init:
            result = await self.client.__aenter__()
            
            mock_init.assert_called_once()
            assert result == self.client
    
    @pytest.mark.asyncio
    async def test_context_manager_exit(self):
        """Test async context manager __aexit__."""
        with patch.object(self.client, 'close', new_callable=AsyncMock) as mock_close:
            await self.client.__aexit__(None, None, None)
            
            mock_close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_client(self):
        """Test client connection closure."""
        mock_http_client = AsyncMock()
        mock_http_client.close = AsyncMock()  # Fix: Use close() not aclose()
        self.client.client = mock_http_client
        
        await self.client.close()
        
        mock_http_client.close.assert_called_once()  # Fix: Check close() method
    
    @pytest.mark.asyncio
    async def test_close_client_no_connection(self):
        """Test client closure when no connection exists."""
        self.client.client = None
        
        # Should not raise exception
        await self.client.close()
    
    @pytest.mark.asyncio
    async def test_ping_success(self):
        """Test successful ping operation."""
        mock_response = Mock()
        mock_response.status_code = 200
        
        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        self.client.client = mock_http_client
        
        result = await self.client.ping()
        
        assert result is True
        mock_http_client.get.assert_called_once_with("/api/info")  # Fix: Correct endpoint
    
    @pytest.mark.asyncio
    async def test_ping_failure(self):
        """Test ping operation failure."""
        mock_response = Mock()
        mock_response.status_code = 500
        
        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response
        self.client.client = mock_http_client
        
        result = await self.client.ping()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_ping_exception(self):
        """Test ping operation with exception."""
        mock_http_client = AsyncMock()
        mock_http_client.get.side_effect = Exception("Network error")
        self.client.client = mock_http_client
        
        result = await self.client.ping()
        
        assert result is False


class TestTerminusDBClientDatabaseOperations:
    """Test suite for TerminusDBClient database operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('terminus_client.create_terminus_client'), \
             patch('terminus_client.create_secure_client'):
            
            self.client = TerminusDBClient(endpoint="http://test.local", use_connection_pool=False)
            
            # Setup mock HTTP client
            self.mock_http_client = AsyncMock()
            self.client.client = self.mock_http_client
    
    @pytest.mark.asyncio
    async def test_create_database_success(self):
        """Test successful database creation."""
        db_name = "test_db"
        label = "Test Database"
        
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.raise_for_status = Mock()  # Fix: Add raise_for_status mock
        
        self.mock_http_client.post.return_value = mock_response
        
        result = await self.client.create_database(db_name, label)
        
        # Verify API call
        self.mock_http_client.post.assert_called_once()
        call_args = self.mock_http_client.post.call_args
        
        assert call_args[0][0] == f"/api/db/admin/{db_name}"  # Fix: Exact URL match
        assert result is True  # Fix: Should return True for success
    
    @pytest.mark.asyncio
    async def test_create_database_without_label(self):
        """Test database creation without label."""
        db_name = "test_db"
        
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.raise_for_status = Mock()
        
        self.mock_http_client.post.return_value = mock_response
        
        result = await self.client.create_database(db_name)
        
        # Verify API call
        self.mock_http_client.post.assert_called_once()
        call_args = self.mock_http_client.post.call_args
        
        # Verify payload has default label
        payload = call_args.kwargs.get("json", {})
        assert payload.get("label") == f"{db_name} Database"  # Fix: Default label logic
        assert result is True
    
    @pytest.mark.asyncio
    async def test_create_database_already_exists(self):
        """Test database creation when database already exists."""
        db_name = "test_db"
        
        # Mock HTTPStatusError for 400 response
        mock_response = Mock()
        mock_response.status_code = 400
        
        http_error = httpx.HTTPStatusError("Bad Request", request=Mock(), response=mock_response)
        
        self.mock_http_client.post.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        result = await self.client.create_database(db_name)
        
        # Should return False for existing database
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_database_success(self):
        """Test successful database deletion."""
        db_name = "test_db"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        
        self.mock_http_client.delete.return_value = mock_response
        
        await self.client.delete_database(db_name)
        
        # Verify API call
        self.mock_http_client.delete.assert_called_once_with(f"/api/db/admin/{db_name}")
    
    @pytest.mark.asyncio
    async def test_delete_database_not_found(self):
        """Test database deletion when database doesn't exist."""
        db_name = "nonexistent_db"
        
        mock_response = Mock()
        mock_response.status_code = 404
        
        http_error = httpx.HTTPStatusError("Not Found", request=Mock(), response=mock_response)
        
        self.mock_http_client.delete.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(httpx.HTTPStatusError):  # Fix: Expect specific exception
            await self.client.delete_database(db_name)
    
    @pytest.mark.asyncio
    async def test_get_databases_success(self):
        """Test successful databases listing."""
        mock_databases = [
            {"name": "db1", "label": "Database 1"},
            {"name": "db2", "label": "Database 2"}
        ]
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_databases
        
        self.mock_http_client.get.return_value = mock_response
        
        result = await self.client.get_databases()
        
        # Verify API call to correct endpoint
        self.mock_http_client.get.assert_called_once_with("/api/organizations")  # Fix: Correct endpoint
        assert result == mock_databases
    
    @pytest.mark.asyncio
    async def test_get_databases_fallback(self):
        """Test databases listing with fallback to info endpoint."""
        mock_response_orgs = Mock()
        mock_response_orgs.status_code = 404  # Organizations endpoint fails
        
        mock_response_info = Mock()
        mock_response_info.status_code = 200
        mock_response_info.json.return_value = {"status": "ok"}
        
        # First call fails, second succeeds
        self.mock_http_client.get.side_effect = [mock_response_orgs, mock_response_info]
        
        result = await self.client.get_databases()
        
        # Should call both endpoints
        expected_calls = [call("/api/organizations"), call("/api/info")]
        self.mock_http_client.get.assert_has_calls(expected_calls)
        assert result == [{"name": "admin", "status": "available"}]  # Fix: Fallback result


class TestTerminusDBClientQueryOperations:
    """Test suite for TerminusDBClient query operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('terminus_client.create_terminus_client'), \
             patch('terminus_client.create_secure_client'):
            
            self.client = TerminusDBClient(endpoint="http://test.local", use_connection_pool=False)
            
            # Setup mock HTTP client
            self.mock_http_client = AsyncMock()
            self.client.client = self.mock_http_client
    
    @pytest.mark.asyncio
    async def test_query_success(self):
        """Test successful query execution."""
        db_name = "test_db"
        query = "SELECT ?x WHERE { ?x rdf:type @schema:Person }"
        commit_msg = "Test query"
        
        mock_results = {"bindings": [{"x": "person1"}, {"x": "person2"}]}
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_results
        mock_response.raise_for_status = Mock()
        
        self.mock_http_client.post.return_value = mock_response
        
        result = await self.client.query(db_name, query, commit_msg)
        
        # Verify API call
        self.mock_http_client.post.assert_called_once()
        call_args = self.mock_http_client.post.call_args
        
        assert call_args[0][0] == f"/api/woql/admin/{db_name}"
        assert result == mock_results
    
    @pytest.mark.asyncio
    async def test_query_without_commit_message(self):
        """Test query execution without commit message."""
        db_name = "test_db"
        query = "SELECT ?x WHERE { ?x rdf:type @schema:Person }"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"bindings": []}
        mock_response.raise_for_status = Mock()
        
        self.mock_http_client.post.return_value = mock_response
        
        result = await self.client.query(db_name, query)
        
        # Should work without commit message
        assert result == {"bindings": []}
    
    @pytest.mark.asyncio
    async def test_query_syntax_error(self):
        """Test query execution with syntax error."""
        db_name = "test_db"
        query = "INVALID QUERY SYNTAX"
        
        mock_response = Mock()
        mock_response.status_code = 400
        
        http_error = httpx.HTTPStatusError("Bad Request", request=Mock(), response=mock_response)
        
        self.mock_http_client.post.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(httpx.HTTPStatusError):  # Fix: Expect specific exception
            await self.client.query(db_name, query)


class TestTerminusDBClientSchemaOperations:
    """Test suite for TerminusDBClient schema operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('terminus_client.create_terminus_client'), \
             patch('terminus_client.create_secure_client'):
            
            self.client = TerminusDBClient(endpoint="http://test.local", use_connection_pool=False)
            
            # Setup mock HTTP client
            self.mock_http_client = AsyncMock()
            self.client.client = self.mock_http_client
    
    @pytest.mark.asyncio
    async def test_get_schema_success(self):
        """Test successful schema retrieval."""
        db_name = "test_db"
        mock_schema = {
            "@type": "Schema",
            "classes": ["Person", "Organization"],
            "properties": ["name", "email"]
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_schema
        mock_response.raise_for_status = Mock()
        
        self.mock_http_client.get.return_value = mock_response
        
        result = await self.client.get_schema(db_name)
        
        # Verify API call
        self.mock_http_client.get.assert_called_once_with(f"/api/schema/admin/{db_name}")
        assert result == mock_schema
    
    @pytest.mark.asyncio
    async def test_get_schema_not_found(self):
        """Test schema retrieval when schema doesn't exist."""
        db_name = "nonexistent_db"
        
        mock_response = Mock()
        mock_response.status_code = 404
        
        http_error = httpx.HTTPStatusError("Not Found", request=Mock(), response=mock_response)
        
        self.mock_http_client.get.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(httpx.HTTPStatusError):  # Fix: Expect specific exception
            await self.client.get_schema(db_name)
    
    @pytest.mark.asyncio
    async def test_update_schema_success(self):
        """Test successful schema update."""
        db_name = "test_db"
        schema = {
            "@type": "Class",
            "@id": "Person",
            "name": {"@type": "xsd:string"}
        }
        commit_msg = "Add Person class"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "updated"}
        mock_response.raise_for_status = Mock()
        
        self.mock_http_client.post.return_value = mock_response
        
        result = await self.client.update_schema(db_name, schema, commit_msg)
        
        # Verify API call
        self.mock_http_client.post.assert_called_once()
        call_args = self.mock_http_client.post.call_args
        
        assert call_args[0][0] == f"/api/schema/admin/{db_name}"
        assert result == {"status": "updated"}
    
    @pytest.mark.asyncio
    async def test_update_schema_invalid(self):
        """Test schema update with invalid schema."""
        db_name = "test_db"
        schema = {"invalid": "schema"}
        commit_msg = "Invalid update"
        
        mock_response = Mock()
        mock_response.status_code = 400
        
        http_error = httpx.HTTPStatusError("Bad Request", request=Mock(), response=mock_response)
        
        self.mock_http_client.post.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(httpx.HTTPStatusError):  # Fix: Expect specific exception
            await self.client.update_schema(db_name, schema, commit_msg)


# Test data factories
class TerminusDBTestDataFactory:
    """Factory for creating test data objects."""
    
    @staticmethod
    def create_database_info(
        name: str = "test_db",
        label: Optional[str] = None,
        comment: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create database info dictionary."""
        return {
            "name": name,
            "label": label or name,
            "comment": comment or f"Test database {name}",
            "created": "2024-01-01T00:00:00Z"
        }
    
    @staticmethod
    def create_query_result(
        variables: List[str] = None,
        bindings: List[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create query result dictionary."""
        variables = variables or ["x", "y"]
        bindings = bindings or [
            {"x": "value1", "y": "value2"},
            {"x": "value3", "y": "value4"}
        ]
        
        return {
            "variables": variables,
            "bindings": bindings
        }
    
    @staticmethod
    def create_schema_definition(
        classes: List[str] = None,
        properties: List[str] = None
    ) -> Dict[str, Any]:
        """Create schema definition dictionary."""
        classes = classes or ["Person", "Organization"]
        properties = properties or ["name", "email", "description"]
        
        return {
            "@type": "Schema",
            "@context": {
                "@base": "http://example.org/",
                "@vocab": "http://example.org/schema#"
            },
            "classes": classes,
            "properties": properties
        }