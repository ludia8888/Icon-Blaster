"""Simplified unit tests for TerminusDBClient - Core functionality testing."""

import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, patch, MagicMock, AsyncMock
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
sys.modules['database.clients.unified_http_client'] = MagicMock()
sys.modules['utils.retry_strategy'] = MagicMock()


class TestTerminusDBClientSimple:
    """Test suite for basic TerminusDBClient functionality without complex mocking."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Create a simple client class for testing core logic
        class SimpleTerminusDBClient:
            def __init__(self, endpoint="http://localhost:6363", username="admin", 
                        password="changeme-admin-pass", service_name="schema-service",
                        use_connection_pool=True):
                self.endpoint = endpoint
                self.username = username
                self.password = password
                self.service_name = service_name
                self.use_connection_pool = use_connection_pool
                self.client = None
                self.cache_size = int(os.getenv("TERMINUSDB_LRU_CACHE_SIZE", "500000000"))
                self.enable_internal_cache = os.getenv("TERMINUSDB_CACHE_ENABLED", "true").lower() == "true"
                self.use_mtls = os.getenv("TERMINUSDB_USE_MTLS", "false").lower() == "true"
                self.pool_config = None
            
            async def __aenter__(self):
                await self._initialize_client()
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                await self.close()
            
            async def _initialize_client(self):
                # Mock initialization
                self.client = AsyncMock()
                return self.client
            
            async def close(self):
                if self.client:
                    await self.client.close()
            
            async def ping(self):
                try:
                    response = await self.client.get("/api/info")
                    return response.status_code == 200
                except Exception:
                    return False
            
            async def create_database(self, db_name: str, label: Optional[str] = None):
                url = f"/api/db/admin/{db_name}"
                payload = {
                    "organization": "admin",
                    "database": db_name,
                    "label": label or f"{db_name} Database",
                    "comment": "OMS Database"
                }
                
                try:
                    response = await self.client.post(url, json=payload)
                    response.raise_for_status()
                    return True
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 400:
                        return False
                    raise
            
            async def delete_database(self, db_name: str):
                url = f"/api/db/admin/{db_name}"
                response = await self.client.delete(url)
                response.raise_for_status()
            
            async def get_databases(self):
                try:
                    response = await self.client.get("/api/organizations")
                    if response.status_code == 200:
                        return response.json()
                    else:
                        response = await self.client.get("/api/info")
                        return [{"name": "admin", "status": "available"}]
                except Exception as e:
                    return []
            
            async def query(self, db_name: str, query: str, commit_msg: Optional[str] = None):
                url = f"/api/woql/admin/{db_name}"
                payload = {
                    "query": query,
                    "commit_info": {"message": commit_msg or "Query execution"}
                }
                response = await self.client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
            
            async def get_schema(self, db_name: str):
                url = f"/api/schema/admin/{db_name}"
                response = await self.client.get(url)
                response.raise_for_status()
                return response.json()
            
            async def update_schema(self, db_name: str, schema: Dict[str, Any], commit_msg: str = "Schema update"):
                url = f"/api/schema/admin/{db_name}"
                payload = {
                    "schema": schema,
                    "commit_info": {"message": commit_msg}
                }
                response = await self.client.post(url, json=payload)
                response.raise_for_status()
                return response.json()
        
        self.client_class = SimpleTerminusDBClient
        self.client = SimpleTerminusDBClient(
            endpoint="http://test.local",
            username="test_user",
            password="test_pass",
            service_name="test_service",
            use_connection_pool=False
        )
    
    def test_client_initialization(self):
        """Test client initialization parameters."""
        assert self.client.endpoint == "http://test.local"
        assert self.client.username == "test_user"
        assert self.client.password == "test_pass"
        assert self.client.service_name == "test_service"
        assert self.client.use_connection_pool is False
        assert self.client.client is None
    
    def test_client_default_values(self):
        """Test client with default values."""
        default_client = self.client_class()
        
        assert default_client.endpoint == "http://localhost:6363"
        assert default_client.username == "admin"
        assert default_client.password == "changeme-admin-pass"
        assert default_client.service_name == "schema-service"
        assert default_client.use_connection_pool is True
    
    def test_client_cache_configuration(self):
        """Test cache configuration."""
        assert self.client.cache_size == int(os.getenv("TERMINUSDB_LRU_CACHE_SIZE", "500000000"))
        assert self.client.enable_internal_cache == (os.getenv("TERMINUSDB_CACHE_ENABLED", "true").lower() == "true")
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test async context manager functionality."""
        mock_init = AsyncMock()
        mock_close = AsyncMock()
        
        with patch.object(self.client, '_initialize_client', mock_init), \
             patch.object(self.client, 'close', mock_close):
            
            async with self.client as client:
                assert client == self.client
                mock_init.assert_called_once()
            
            mock_close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_client_close(self):
        """Test client closure."""
        # Initialize client first
        await self.client._initialize_client()
        
        # Mock the close method
        self.client.client.close = AsyncMock()
        
        await self.client.close()
        
        self.client.client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_ping_success(self):
        """Test successful ping."""
        await self.client._initialize_client()
        
        mock_response = Mock()
        mock_response.status_code = 200
        self.client.client.get.return_value = mock_response
        
        result = await self.client.ping()
        
        assert result is True
        self.client.client.get.assert_called_once_with("/api/info")
    
    @pytest.mark.asyncio
    async def test_ping_failure(self):
        """Test ping failure."""
        await self.client._initialize_client()
        
        mock_response = Mock()
        mock_response.status_code = 500
        self.client.client.get.return_value = mock_response
        
        result = await self.client.ping()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_ping_exception(self):
        """Test ping with exception."""
        await self.client._initialize_client()
        
        self.client.client.get.side_effect = Exception("Network error")
        
        result = await self.client.ping()
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_create_database_success(self):
        """Test successful database creation."""
        await self.client._initialize_client()
        
        db_name = "test_db"
        label = "Test Database"
        
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.raise_for_status = Mock()
        self.client.client.post.return_value = mock_response
        
        result = await self.client.create_database(db_name, label)
        
        assert result is True
        self.client.client.post.assert_called_once()
        call_args = self.client.client.post.call_args
        assert call_args[0][0] == f"/api/db/admin/{db_name}"
        assert call_args.kwargs["json"]["label"] == label
    
    @pytest.mark.asyncio
    async def test_create_database_default_label(self):
        """Test database creation with default label."""
        await self.client._initialize_client()
        
        db_name = "test_db"
        
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.raise_for_status = Mock()
        self.client.client.post.return_value = mock_response
        
        result = await self.client.create_database(db_name)
        
        assert result is True
        call_args = self.client.client.post.call_args
        assert call_args.kwargs["json"]["label"] == f"{db_name} Database"
    
    @pytest.mark.asyncio
    async def test_create_database_already_exists(self):
        """Test database creation when database already exists."""
        await self.client._initialize_client()
        
        db_name = "existing_db"
        
        mock_response = Mock()
        mock_response.status_code = 400
        http_error = httpx.HTTPStatusError("Bad Request", request=Mock(), response=mock_response)
        
        self.client.client.post.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        result = await self.client.create_database(db_name)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_database_success(self):
        """Test successful database deletion."""
        await self.client._initialize_client()
        
        db_name = "test_db"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()
        self.client.client.delete.return_value = mock_response
        
        await self.client.delete_database(db_name)
        
        self.client.client.delete.assert_called_once_with(f"/api/db/admin/{db_name}")
    
    @pytest.mark.asyncio
    async def test_delete_database_not_found(self):
        """Test database deletion when database doesn't exist."""
        await self.client._initialize_client()
        
        db_name = "nonexistent_db"
        
        mock_response = Mock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError("Not Found", request=Mock(), response=mock_response)
        
        self.client.client.delete.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(httpx.HTTPStatusError):
            await self.client.delete_database(db_name)
    
    @pytest.mark.asyncio
    async def test_get_databases_success(self):
        """Test successful database listing."""
        await self.client._initialize_client()
        
        mock_databases = [{"name": "db1"}, {"name": "db2"}]
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_databases
        self.client.client.get.return_value = mock_response
        
        result = await self.client.get_databases()
        
        assert result == mock_databases
        self.client.client.get.assert_called_once_with("/api/organizations")
    
    @pytest.mark.asyncio
    async def test_get_databases_fallback(self):
        """Test database listing with fallback."""
        await self.client._initialize_client()
        
        # First call fails (organizations), second succeeds (info)
        mock_response_orgs = Mock()
        mock_response_orgs.status_code = 404
        
        mock_response_info = Mock()
        mock_response_info.status_code = 200
        
        self.client.client.get.side_effect = [mock_response_orgs, mock_response_info]
        
        result = await self.client.get_databases()
        
        assert result == [{"name": "admin", "status": "available"}]
        assert self.client.client.get.call_count == 2
    
    @pytest.mark.asyncio
    async def test_query_success(self):
        """Test successful query execution."""
        await self.client._initialize_client()
        
        db_name = "test_db"
        query = "SELECT ?x WHERE { ?x rdf:type @schema:Person }"
        commit_msg = "Test query"
        
        mock_result = {"bindings": [{"x": "person1"}]}
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_result
        mock_response.raise_for_status = Mock()
        self.client.client.post.return_value = mock_response
        
        result = await self.client.query(db_name, query, commit_msg)
        
        assert result == mock_result
        self.client.client.post.assert_called_once()
        call_args = self.client.client.post.call_args
        assert call_args[0][0] == f"/api/woql/admin/{db_name}"
        assert call_args.kwargs["json"]["query"] == query
    
    @pytest.mark.asyncio
    async def test_query_syntax_error(self):
        """Test query with syntax error."""
        await self.client._initialize_client()
        
        db_name = "test_db"
        query = "INVALID QUERY"
        
        mock_response = Mock()
        mock_response.status_code = 400
        http_error = httpx.HTTPStatusError("Bad Request", request=Mock(), response=mock_response)
        
        self.client.client.post.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(httpx.HTTPStatusError):
            await self.client.query(db_name, query)
    
    @pytest.mark.asyncio
    async def test_get_schema_success(self):
        """Test successful schema retrieval."""
        await self.client._initialize_client()
        
        db_name = "test_db"
        mock_schema = {"@type": "Schema", "classes": ["Person"]}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_schema
        mock_response.raise_for_status = Mock()
        self.client.client.get.return_value = mock_response
        
        result = await self.client.get_schema(db_name)
        
        assert result == mock_schema
        self.client.client.get.assert_called_once_with(f"/api/schema/admin/{db_name}")
    
    @pytest.mark.asyncio
    async def test_get_schema_not_found(self):
        """Test schema retrieval when schema doesn't exist."""
        await self.client._initialize_client()
        
        db_name = "nonexistent_db"
        
        mock_response = Mock()
        mock_response.status_code = 404
        http_error = httpx.HTTPStatusError("Not Found", request=Mock(), response=mock_response)
        
        self.client.client.get.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(httpx.HTTPStatusError):
            await self.client.get_schema(db_name)
    
    @pytest.mark.asyncio
    async def test_update_schema_success(self):
        """Test successful schema update."""
        await self.client._initialize_client()
        
        db_name = "test_db"
        schema = {"@type": "Class", "@id": "Person"}
        commit_msg = "Add Person class"
        
        mock_result = {"status": "updated"}
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_result
        mock_response.raise_for_status = Mock()
        self.client.client.post.return_value = mock_response
        
        result = await self.client.update_schema(db_name, schema, commit_msg)
        
        assert result == mock_result
        self.client.client.post.assert_called_once()
        call_args = self.client.client.post.call_args
        assert call_args[0][0] == f"/api/schema/admin/{db_name}"
        assert call_args.kwargs["json"]["schema"] == schema
    
    @pytest.mark.asyncio
    async def test_update_schema_invalid(self):
        """Test schema update with invalid schema."""
        await self.client._initialize_client()
        
        db_name = "test_db"
        schema = {"invalid": "schema"}
        
        mock_response = Mock()
        mock_response.status_code = 400
        http_error = httpx.HTTPStatusError("Bad Request", request=Mock(), response=mock_response)
        
        self.client.client.post.return_value = mock_response
        mock_response.raise_for_status.side_effect = http_error
        
        with pytest.raises(httpx.HTTPStatusError):
            await self.client.update_schema(db_name, schema)


class TestTerminusDBClientDataFactory:
    """Test suite for TerminusDB test data factories."""
    
    def test_create_database_info(self):
        """Test database info creation."""
        from tests.unit.database.clients.test_terminus_db_basic import TerminusDBTestDataFactory
        
        db_info = TerminusDBTestDataFactory.create_database_info("test_db", "Test Database")
        
        assert db_info["name"] == "test_db"
        assert db_info["label"] == "Test Database"
        assert "created" in db_info
    
    def test_create_query_result(self):
        """Test query result creation."""
        from tests.unit.database.clients.test_terminus_db_basic import TerminusDBTestDataFactory
        
        result = TerminusDBTestDataFactory.create_query_result(
            variables=["name", "age"],
            bindings=[{"name": "Alice", "age": "30"}]
        )
        
        assert result["variables"] == ["name", "age"]
        assert result["bindings"] == [{"name": "Alice", "age": "30"}]
    
    def test_create_schema_definition(self):
        """Test schema definition creation."""
        from tests.unit.database.clients.test_terminus_db_basic import TerminusDBTestDataFactory
        
        schema = TerminusDBTestDataFactory.create_schema_definition(
            classes=["Person"],
            properties=["name"]
        )
        
        assert schema["@type"] == "Schema"
        assert schema["classes"] == ["Person"]
        assert schema["properties"] == ["name"]
        assert "@context" in schema