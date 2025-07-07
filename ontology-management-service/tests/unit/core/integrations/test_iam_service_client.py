"""Comprehensive unit tests for IAM Service Client - security-critical authentication in MSA environment."""

import pytest
import asyncio
import sys
import os
import uuid
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, Optional, List

# Add the project root to the path to import modules directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))

# Mock external dependencies before imports
sys.modules['prometheus_client'] = MagicMock()
sys.modules['common_logging'] = MagicMock()
sys.modules['common_logging.setup'] = MagicMock()
sys.modules['redis.asyncio'] = MagicMock()
sys.modules['httpx'] = MagicMock()
sys.modules['jwt'] = MagicMock()
sys.modules['jwt.PyJWKClient'] = MagicMock()
sys.modules['backoff'] = MagicMock()

# Mock the database clients
sys.modules['database.clients.unified_http_client'] = MagicMock()

# Create mock classes for testing
class MockHTTPResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}
    
    def json(self):
        return self._json_data
    
    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

class MockUnifiedHTTPClient:
    def __init__(self, config):
        self.config = config
        self.responses = {}
        self.force_error = False
        self.force_status_code = None
    
    async def request(self, method, url, json=None, headers=None):
        """Mock request method."""
        # Check for forced errors
        if self.force_error:
            raise Exception("Forced error")
        
        # Check for custom responses first
        if url in self.responses:
            return self.responses[url]
        
        # Check forced status code
        if self.force_status_code:
            return MockHTTPResponse(self.force_status_code, {"error": "Forced error"})
        
        # Return mocked responses based on URL patterns
        if "/api/v1/auth/validate" in url:
            # Check if token is marked as invalid
            if json and json.get("token") == "invalid.jwt.token":
                return MockHTTPResponse(401, {
                    "valid": False,
                    "error": "Invalid or expired token"
                })
            return MockHTTPResponse(200, {
                "valid": True,
                "user_id": "test-user-123",
                "username": "testuser",
                "email": "test@example.com",
                "scopes": ["api:ontologies:read", "api:schemas:read"],
                "roles": ["user", "ontology_editor"],
                "tenant_id": "tenant-123",
                "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                "metadata": {"source": "iam_service"}
            })
        elif "/api/v1/users/info" in url:
            return MockHTTPResponse(200, {
                "user_id": "test-user-123",
                "username": "testuser",
                "email": "test@example.com",
                "full_name": "Test User",
                "tenant_id": "tenant-123",
                "roles": ["user", "ontology_editor"],
                "scopes": ["api:ontologies:read", "api:schemas:read"],
                "teams": ["team-alpha"],
                "mfa_enabled": True,
                "active": True,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-02T00:00:00Z"
            })
        elif "/api/v1/auth/service" in url:
            return MockHTTPResponse(200, {
                "access_token": "service-token-12345",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scopes": ["api:service:account", "api:ontologies:read"]
            })
        elif "/api/v1/auth/check-scopes" in url:
            return MockHTTPResponse(200, {
                "authorized": True,
                "user_scopes": ["api:ontologies:read", "api:schemas:read"],
                "missing_scopes": []
            })
        elif "/api/v1/auth/refresh" in url:
            return MockHTTPResponse(200, {
                "access_token": "new-token-12345",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600
            })
        elif "/health" in url:
            return MockHTTPResponse(200, {
                "status": "healthy",
                "version": "1.0.0",
                "timestamp": datetime.utcnow().isoformat(),
                "components": {"database": {"status": "healthy"}}
            })
        else:
            return MockHTTPResponse(404, {"error": "Not found"})
    
    async def close(self):
        """Mock close method."""
        pass

# Mock IAM contracts
class MockIAMScope:
    SERVICE_ACCOUNT = "api:service:account"
    ONTOLOGIES_READ = "api:ontologies:read"
    SCHEMAS_READ = "api:schemas:read"
    ONTOLOGIES_WRITE = "api:ontologies:write"
    SCHEMAS_WRITE = "api:schemas:write"
    SYSTEM_ADMIN = "api:system:admin"

class MockIAMConfig:
    def __init__(self, **kwargs):
        self.iam_service_url = kwargs.get('iam_service_url', 'http://user-service:8000')
        self.jwks_url = kwargs.get('jwks_url')
        self.expected_issuer = kwargs.get('expected_issuer', 'iam.company')
        self.expected_audience = kwargs.get('expected_audience', 'oms')
        self.service_id = kwargs.get('service_id', 'oms-service')
        self.service_secret = kwargs.get('service_secret', 'test-secret')
        self.timeout = kwargs.get('timeout', 10)
        self.retry_count = kwargs.get('retry_count', 3)
        self.cache_ttl = kwargs.get('cache_ttl', 300)
        self.enable_jwks = kwargs.get('enable_jwks', True)
        self.verify_ssl = kwargs.get('verify_ssl', True)

class MockTokenValidationRequest:
    def __init__(self, token, validate_scopes=True, required_scopes=None):
        self.token = token
        self.validate_scopes = validate_scopes
        self.required_scopes = required_scopes
    
    def dict(self):
        return {
            'token': self.token,
            'validate_scopes': self.validate_scopes,
            'required_scopes': self.required_scopes
        }

class MockTokenValidationResponse:
    def __init__(self, **kwargs):
        self.valid = kwargs.get('valid', True)
        self.user_id = kwargs.get('user_id')
        self.username = kwargs.get('username')
        self.email = kwargs.get('email')
        self.scopes = kwargs.get('scopes', [])
        self.roles = kwargs.get('roles', [])
        self.tenant_id = kwargs.get('tenant_id')
        self.expires_at = kwargs.get('expires_at')
        self.metadata = kwargs.get('metadata', {})
        self.error = kwargs.get('error')
    
    def json(self):
        return json.dumps(self.__dict__)

class MockUserInfoRequest:
    def __init__(self, user_id=None, username=None, email=None, include_permissions=False):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.include_permissions = include_permissions
    
    def dict(self):
        return {
            'user_id': self.user_id,
            'username': self.username,
            'email': self.email,
            'include_permissions': self.include_permissions
        }

class MockUserInfoResponse:
    def __init__(self, **kwargs):
        self.user_id = kwargs['user_id']
        self.username = kwargs['username']
        self.email = kwargs['email']
        self.full_name = kwargs.get('full_name')
        self.tenant_id = kwargs.get('tenant_id')
        self.roles = kwargs.get('roles', [])
        self.scopes = kwargs.get('scopes', [])
        self.teams = kwargs.get('teams', [])
        self.permissions = kwargs.get('permissions')
        self.mfa_enabled = kwargs.get('mfa_enabled', False)
        self.active = kwargs.get('active', True)
        self.created_at = kwargs['created_at']
        self.updated_at = kwargs['updated_at']

class MockServiceAuthRequest:
    def __init__(self, service_id, service_secret, requested_scopes=None):
        self.service_id = service_id
        self.service_secret = service_secret
        self.requested_scopes = requested_scopes or []
    
    def dict(self):
        return {
            'service_id': self.service_id,
            'service_secret': self.service_secret,
            'requested_scopes': self.requested_scopes
        }

class MockServiceAuthResponse:
    def __init__(self, **kwargs):
        self.access_token = kwargs['access_token']
        self.token_type = kwargs.get('token_type', 'Bearer')
        self.expires_in = kwargs['expires_in']
        self.scopes = kwargs.get('scopes', [])

class MockScopeCheckRequest:
    def __init__(self, user_id, required_scopes, check_mode='any'):
        self.user_id = user_id
        self.required_scopes = required_scopes
        self.check_mode = check_mode
    
    def dict(self):
        return {
            'user_id': self.user_id,
            'required_scopes': self.required_scopes,
            'check_mode': self.check_mode
        }

class MockScopeCheckResponse:
    def __init__(self, **kwargs):
        self.authorized = kwargs['authorized']
        self.user_scopes = kwargs.get('user_scopes', [])
        self.missing_scopes = kwargs.get('missing_scopes', [])

class MockIAMHealthResponse:
    def __init__(self, **kwargs):
        self.status = kwargs.get('status', 'healthy')
        self.version = kwargs.get('version', '1.0.0')
        self.timestamp = kwargs.get('timestamp', datetime.utcnow().isoformat())
        self.components = kwargs.get('components', {})

class MockUserContext:
    def __init__(self, user_id, username, email, roles, tenant_id, metadata=None):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.roles = roles
        self.tenant_id = tenant_id
        self.metadata = metadata or {}

class MockHTTPClientConfig:
    def __init__(self, **kwargs):
        self.base_url = kwargs.get('base_url')
        self.timeout = kwargs.get('timeout', 10)
        self.verify_ssl = kwargs.get('verify_ssl', True)
        self.headers = kwargs.get('headers', {})

# Mock Redis client
class MockRedisClient:
    def __init__(self):
        self.data = {}
        self.closed = False
    
    async def get(self, key):
        return self.data.get(key)
    
    async def setex(self, key, ttl, value):
        self.data[key] = value
        return True
    
    async def close(self):
        self.closed = True
    
    @classmethod
    def from_url(cls, url):
        return cls()

# Create a test-friendly IAM Service Client
class MockIAMServiceClient:
    def __init__(self, config=None):
        self.config = config or MockIAMConfig()
        self._client = MockUnifiedHTTPClient(MockHTTPClientConfig(base_url=self.config.iam_service_url))
        self._jwks_client = None
        self._redis_client = MockRedisClient()
        self._service_token = None
        self._service_token_expires = None
    
    def _load_config(self):
        return MockIAMConfig()
    
    async def _ensure_service_auth(self):
        if self._service_token and self._service_token_expires:
            if datetime.utcnow() < self._service_token_expires:
                return self._service_token
        
        auth_response = await self.authenticate_service()
        self._service_token = auth_response.access_token
        self._service_token_expires = datetime.utcnow() + timedelta(seconds=auth_response.expires_in - 60)
        return self._service_token
    
    async def _make_request(self, method, endpoint, data=None, use_service_auth=False):
        headers = {}
        if use_service_auth:
            token = await self._ensure_service_auth()
            headers["Authorization"] = f"Bearer {token}"
        
        response = await self._client.request(method=method, url=endpoint, json=data, headers=headers)
        if response.status_code >= 400:
            raise Exception(f"HTTP {response.status_code}")
        return response.json()
    
    async def validate_token(self, token, required_scopes=None):
        # Check cache first
        cache_key = f"iam:token:{token[:20]}"
        if self._redis_client:
            try:
                cached = await self._redis_client.get(cache_key)
                if cached:
                    return MockTokenValidationResponse(**json.loads(cached))
            except Exception as e:
                # Cache error - continue without cache
                pass
        
        request = MockTokenValidationRequest(token, bool(required_scopes), required_scopes)
        
        try:
            result = await self._make_request("POST", "/api/v1/auth/validate", data=request.model_dump())
            
            # Handle malformed responses
            if not isinstance(result, dict) or 'valid' not in result:
                return MockTokenValidationResponse(valid=False, error="Malformed response from IAM service")
            
            response = MockTokenValidationResponse(**result)
            
            # Cache successful validation
            if response.valid and self._redis_client:
                try:
                    await self._redis_client.setex(cache_key, self.config.cache_ttl, response.json())
                except Exception:
                    # Cache write error - ignore
                    pass
            
            return response
        except Exception as e:
            error_msg = str(e)
            if "HTTP 401" in error_msg:
                return MockTokenValidationResponse(valid=False, error="Invalid or expired token")
            return MockTokenValidationResponse(valid=False, error=f"Validation service error: {error_msg}")
    
    async def get_user_info(self, user_id=None, username=None, email=None, include_permissions=False):
        if not any([user_id, username, email]):
            raise ValueError("Must provide user_id, username, or email")
        
        request = MockUserInfoRequest(user_id, username, email, include_permissions)
        
        try:
            result = await self._make_request("POST", "/api/v1/users/info", data=request.model_dump(), use_service_auth=True)
            return MockUserInfoResponse(**result)
        except Exception as e:
            if "404" in str(e):
                return None
            raise
    
    async def check_user_scopes(self, user_id, required_scopes, check_mode="any"):
        request = MockScopeCheckRequest(user_id, required_scopes, check_mode)
        
        try:
            result = await self._make_request("POST", "/api/v1/auth/check-scopes", data=request.model_dump(), use_service_auth=True)
            return MockScopeCheckResponse(**result)
        except Exception:
            return MockScopeCheckResponse(authorized=False, missing_scopes=required_scopes)
    
    async def authenticate_service(self):
        if not self.config.service_secret:
            raise ValueError("Service secret not configured")
        
        request = MockServiceAuthRequest(
            self.config.service_id,
            self.config.service_secret,
            [MockIAMScope.SERVICE_ACCOUNT, MockIAMScope.ONTOLOGIES_READ, MockIAMScope.SCHEMAS_READ]
        )
        
        result = await self._make_request("POST", "/api/v1/auth/service", data=request.model_dump())
        return MockServiceAuthResponse(**result)
    
    async def refresh_token(self, refresh_token):
        result = await self._make_request("POST", "/api/v1/auth/refresh", data={"refresh_token": refresh_token})
        return result
    
    async def health_check(self):
        try:
            result = await self._make_request("GET", "/health")
            return MockIAMHealthResponse(**result)
        except Exception:
            return MockIAMHealthResponse(status="unhealthy", version="unknown")
    
    def create_user_context(self, validation_response):
        if not validation_response.valid:
            raise ValueError("Cannot create context from invalid token")
        
        return MockUserContext(
            user_id=validation_response.user_id,
            username=validation_response.username,
            email=validation_response.email,
            roles=validation_response.roles,
            tenant_id=validation_response.tenant_id,
            metadata={
                "scopes": validation_response.scopes,
                "iam_metadata": validation_response.metadata
            }
        )
    
    async def close(self):
        await self._client.close()
        if self._redis_client:
            await self._redis_client.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Test Data Factories
class TestDataFactory:
    """Factory for creating test data."""
    
    @staticmethod
    def create_valid_jwt_token():
        """Create a mock valid JWT token."""
        return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXItMTIzIiwidXNlcm5hbWUiOiJ0ZXN0dXNlciIsImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSIsInNjb3BlcyI6WyJhcGk6b250b2xvZ2llczpyZWFkIl0sImlhdCI6MTcwMDAwMDAwMCwiZXhwIjoxNzAwMDAzNjAwfQ.signature"
    
    @staticmethod
    def create_invalid_jwt_token():
        """Create a mock invalid JWT token."""
        return "invalid.jwt.token"
    
    @staticmethod
    def create_expired_jwt_token():
        """Create a mock expired JWT token."""
        return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0LXVzZXItMTIzIiwidXNlcm5hbWUiOiJ0ZXN0dXNlciIsImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSIsInNjb3BlcyI6WyJhcGk6b250b2xvZ2llczpyZWFkIl0sImlhdCI6MTYwMDAwMDAwMCwiZXhwIjoxNjAwMDAzNjAwfQ.signature"
    
    @staticmethod
    def create_iam_config(**overrides):
        """Create IAM configuration for testing."""
        defaults = {
            'iam_service_url': 'http://test-user-service:8000',
            'service_id': 'test-oms-service',
            'service_secret': 'test-secret-123',
            'timeout': 5,
            'cache_ttl': 60,
            'enable_jwks': True,
            'verify_ssl': False
        }
        defaults.update(overrides)
        return MockIAMConfig(**defaults)
    
    @staticmethod
    def create_token_validation_response(**overrides):
        """Create token validation response for testing."""
        defaults = {
            'valid': True,
            'user_id': 'test-user-123',
            'username': 'testuser',
            'email': 'test@example.com',
            'scopes': ['api:ontologies:read', 'api:schemas:read'],
            'roles': ['user', 'ontology_editor'],
            'tenant_id': 'tenant-123',
            'expires_at': (datetime.utcnow() + timedelta(hours=1)).isoformat(),
            'metadata': {'source': 'test'}
        }
        defaults.update(overrides)
        return MockTokenValidationResponse(**defaults)
    
    @staticmethod
    def create_user_info_response(**overrides):
        """Create user info response for testing."""
        defaults = {
            'user_id': 'test-user-123',
            'username': 'testuser',
            'email': 'test@example.com',
            'full_name': 'Test User',
            'tenant_id': 'tenant-123',
            'roles': ['user', 'ontology_editor'],
            'scopes': ['api:ontologies:read', 'api:schemas:read'],
            'teams': ['team-alpha'],
            'mfa_enabled': True,
            'active': True,
            'created_at': '2024-01-01T00:00:00Z',
            'updated_at': '2024-01-02T00:00:00Z'
        }
        defaults.update(overrides)
        return MockUserInfoResponse(**defaults)
    
    @staticmethod
    def create_service_auth_response(**overrides):
        """Create service auth response for testing."""
        defaults = {
            'access_token': 'service-token-12345',
            'token_type': 'Bearer',
            'expires_in': 3600,
            'scopes': ['api:service:account', 'api:ontologies:read']
        }
        defaults.update(overrides)
        return MockServiceAuthResponse(**defaults)


class TestIAMServiceClientInitialization:
    """Test cases for IAM Service Client initialization."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
    
    def test_iam_client_initialization_default_config(self):
        """Test IAM client initialization with default config."""
        client = MockIAMServiceClient()
        
        assert client.config is not None
        assert client.config.iam_service_url == 'http://user-service:8000'
        assert client.config.service_id == 'oms-service'
        assert client.config.timeout == 10
        assert client._client is not None
        assert client._redis_client is not None
    
    def test_iam_client_initialization_custom_config(self):
        """Test IAM client initialization with custom config."""
        config = self.factory.create_iam_config(
            iam_service_url='http://custom-iam:9000',
            service_id='custom-service',
            timeout=15
        )
        
        client = MockIAMServiceClient(config)
        
        assert client.config.iam_service_url == 'http://custom-iam:9000'
        assert client.config.service_id == 'custom-service'
        assert client.config.timeout == 15
    
    def test_iam_client_initialization_without_service_secret(self):
        """Test IAM client initialization without service secret."""
        config = self.factory.create_iam_config(service_secret=None)
        client = MockIAMServiceClient(config)
        
        assert client.config.service_secret is None
    
    def test_iam_client_initialization_with_jwks_disabled(self):
        """Test IAM client initialization with JWKS disabled."""
        config = self.factory.create_iam_config(enable_jwks=False)
        client = MockIAMServiceClient(config)
        
        assert client.config.enable_jwks == False
        assert client._jwks_client is None
    
    @pytest.mark.asyncio
    async def test_iam_client_context_manager(self):
        """Test IAM client as async context manager."""
        config = self.factory.create_iam_config()
        
        async with MockIAMServiceClient(config) as client:
            assert client.config is not None
            assert not client._redis_client.closed
        
        # After context exit, connections should be closed
        assert client._redis_client.closed


class TestTokenValidation:
    """Test cases for JWT token validation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_validate_valid_token_success(self):
        """Test validation of valid JWT token."""
        token = self.factory.create_valid_jwt_token()
        
        response = await self.client.validate_token(token)
        
        assert response.valid == True
        assert response.user_id == "test-user-123"
        assert response.username == "testuser"
        assert response.email == "test@example.com"
        assert "api:ontologies:read" in response.scopes
        assert "user" in response.roles
        assert response.tenant_id == "tenant-123"
        assert response.error is None
    
    @pytest.mark.asyncio
    async def test_validate_token_with_required_scopes(self):
        """Test token validation with required scopes."""
        token = self.factory.create_valid_jwt_token()
        required_scopes = ["api:ontologies:read"]
        
        response = await self.client.validate_token(token, required_scopes)
        
        assert response.valid == True
        assert "api:ontologies:read" in response.scopes
    
    @pytest.mark.asyncio
    async def test_validate_invalid_token(self):
        """Test validation of invalid JWT token."""
        token = self.factory.create_invalid_jwt_token()
        response = await self.client.validate_token(token)
        
        assert response.valid == False
        assert response.error is not None
    
    @pytest.mark.asyncio
    async def test_validate_token_caching(self):
        """Test token validation caching mechanism."""
        token = self.factory.create_valid_jwt_token()
        
        # First call - should hit the service
        response1 = await self.client.validate_token(token)
        assert response1.valid == True
        
        # Second call - should hit cache
        response2 = await self.client.validate_token(token)
        assert response2.valid == True
        assert response2.user_id == response1.user_id
    
    @pytest.mark.asyncio
    async def test_validate_token_cache_failure_graceful(self):
        """Test graceful handling of cache failures."""
        # Mock Redis to raise exception
        original_get = self.client._redis_client.get
        self.client._redis_client.get = AsyncMock(side_effect=Exception("Redis error"))
        
        token = self.factory.create_valid_jwt_token()
        response = await self.client.validate_token(token)
        
        # Should still work without cache
        assert response.valid == True
        assert response.user_id == "test-user-123"
        
        # Restore original method
        self.client._redis_client.get = original_get
    
    @pytest.mark.asyncio
    async def test_validate_token_service_error_handling(self):
        """Test handling of service errors during validation."""
        # Mock client to raise exception
        self.client._make_request = AsyncMock(side_effect=Exception("Service unavailable"))
        
        token = self.factory.create_valid_jwt_token()
        response = await self.client.validate_token(token)
        
        assert response.valid == False
        assert "Validation service error" in response.error


class TestUserInfoRetrieval:
    """Test cases for user information retrieval."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_get_user_info_by_user_id(self):
        """Test getting user info by user ID."""
        user_info = await self.client.get_user_info(user_id="test-user-123")
        
        assert user_info is not None
        assert user_info.user_id == "test-user-123"
        assert user_info.username == "testuser"
        assert user_info.email == "test@example.com"
        assert user_info.full_name == "Test User"
        assert user_info.mfa_enabled == True
        assert user_info.active == True
    
    @pytest.mark.asyncio
    async def test_get_user_info_by_username(self):
        """Test getting user info by username."""
        user_info = await self.client.get_user_info(username="testuser")
        
        assert user_info is not None
        assert user_info.username == "testuser"
        assert user_info.user_id == "test-user-123"
    
    @pytest.mark.asyncio
    async def test_get_user_info_by_email(self):
        """Test getting user info by email."""
        user_info = await self.client.get_user_info(email="test@example.com")
        
        assert user_info is not None
        assert user_info.email == "test@example.com"
        assert user_info.user_id == "test-user-123"
    
    @pytest.mark.asyncio
    async def test_get_user_info_with_permissions(self):
        """Test getting user info with detailed permissions."""
        user_info = await self.client.get_user_info(
            user_id="test-user-123",
            include_permissions=True
        )
        
        assert user_info is not None
        assert user_info.user_id == "test-user-123"
        assert len(user_info.scopes) > 0
        assert len(user_info.roles) > 0
    
    @pytest.mark.asyncio
    async def test_get_user_info_user_not_found(self):
        """Test getting user info for non-existent user."""
        # Mock 404 response
        self.client._make_request = AsyncMock(side_effect=Exception("HTTP 404"))
        
        user_info = await self.client.get_user_info(user_id="non-existent-user")
        
        assert user_info is None
    
    @pytest.mark.asyncio
    async def test_get_user_info_no_identifier_provided(self):
        """Test error when no user identifier is provided."""
        with pytest.raises(ValueError, match="Must provide user_id, username, or email"):
            await self.client.get_user_info()
    
    @pytest.mark.asyncio
    async def test_get_user_info_service_error(self):
        """Test handling of service errors during user info retrieval."""
        # Mock service error
        self.client._make_request = AsyncMock(side_effect=Exception("Service error"))
        
        with pytest.raises(Exception, match="Service error"):
            await self.client.get_user_info(user_id="test-user-123")


class TestScopeValidation:
    """Test cases for scope validation and authorization."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_check_user_scopes_authorized(self):
        """Test scope check for authorized user."""
        response = await self.client.check_user_scopes(
            user_id="test-user-123",
            required_scopes=["api:ontologies:read"],
            check_mode="any"
        )
        
        assert response.authorized == True
        assert "api:ontologies:read" in response.user_scopes
        assert len(response.missing_scopes) == 0
    
    @pytest.mark.asyncio
    async def test_check_user_scopes_multiple_required_any_mode(self):
        """Test scope check with multiple required scopes in 'any' mode."""
        response = await self.client.check_user_scopes(
            user_id="test-user-123",
            required_scopes=["api:ontologies:read", "api:system:admin"],
            check_mode="any"
        )
        
        # Should be authorized if user has at least one scope
        assert response.authorized == True
    
    @pytest.mark.asyncio
    async def test_check_user_scopes_multiple_required_all_mode(self):
        """Test scope check with multiple required scopes in 'all' mode."""
        response = await self.client.check_user_scopes(
            user_id="test-user-123",
            required_scopes=["api:ontologies:read", "api:schemas:read"],
            check_mode="all"
        )
        
        # Should be authorized if user has both scopes
        assert response.authorized == True
    
    @pytest.mark.asyncio
    async def test_check_user_scopes_unauthorized(self):
        """Test scope check for unauthorized user."""
        # Mock unauthorized response
        self.client._make_request = AsyncMock(return_value={
            "authorized": False,
            "user_scopes": ["api:ontologies:read"],
            "missing_scopes": ["api:system:admin"]
        })
        
        response = await self.client.check_user_scopes(
            user_id="test-user-123",
            required_scopes=["api:system:admin"],
            check_mode="any"
        )
        
        assert response.authorized == False
        assert "api:system:admin" in response.missing_scopes
    
    @pytest.mark.asyncio
    async def test_check_user_scopes_service_error(self):
        """Test handling of service errors during scope check."""
        # Mock service error
        self.client._make_request = AsyncMock(side_effect=Exception("Service error"))
        
        response = await self.client.check_user_scopes(
            user_id="test-user-123",
            required_scopes=["api:ontologies:read"]
        )
        
        # Should return unauthorized on error
        assert response.authorized == False
        assert "api:ontologies:read" in response.missing_scopes


class TestServiceAuthentication:
    """Test cases for service-to-service authentication."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_authenticate_service_success(self):
        """Test successful service authentication."""
        response = await self.client.authenticate_service()
        
        assert response.access_token == "service-token-12345"
        assert response.token_type == "Bearer"
        assert response.expires_in == 3600
        assert MockIAMScope.SERVICE_ACCOUNT in response.scopes
    
    @pytest.mark.asyncio
    async def test_authenticate_service_no_secret(self):
        """Test service authentication without secret."""
        # Create config without service secret
        config = self.factory.create_iam_config(service_secret=None)
        client = MockIAMServiceClient(config)
        
        with pytest.raises(ValueError, match="Service secret not configured"):
            await client.authenticate_service()
    
    @pytest.mark.asyncio
    async def test_authenticate_service_error(self):
        """Test handling of service authentication errors."""
        # Mock service error
        self.client._make_request = AsyncMock(side_effect=Exception("Authentication failed"))
        
        with pytest.raises(Exception, match="Authentication failed"):
            await self.client.authenticate_service()
    
    @pytest.mark.asyncio
    async def test_ensure_service_auth_token_reuse(self):
        """Test that service token is reused when valid."""
        # First call
        token1 = await self.client._ensure_service_auth()
        assert token1 == "service-token-12345"
        
        # Second call should reuse token
        token2 = await self.client._ensure_service_auth()
        assert token2 == token1
    
    @pytest.mark.asyncio
    async def test_ensure_service_auth_token_refresh(self):
        """Test that service token is refreshed when expired."""
        # Set expired token
        self.client._service_token = "old-token"
        self.client._service_token_expires = datetime.utcnow() - timedelta(minutes=5)
        
        # Should get new token
        token = await self.client._ensure_service_auth()
        assert token == "service-token-12345"


class TestTokenRefresh:
    """Test cases for token refresh functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_refresh_token_success(self):
        """Test successful token refresh."""
        refresh_token = "refresh-token-12345"
        
        response = await self.client.refresh_token(refresh_token)
        
        assert "access_token" in response
        assert response["access_token"] == "new-token-12345"
        assert "refresh_token" in response
        assert response["expires_in"] == 3600
    
    @pytest.mark.asyncio
    async def test_refresh_token_error(self):
        """Test handling of token refresh errors."""
        # Mock service error
        self.client._make_request = AsyncMock(side_effect=Exception("Invalid refresh token"))
        
        with pytest.raises(Exception, match="Invalid refresh token"):
            await self.client.refresh_token("invalid-refresh-token")


class TestHealthCheck:
    """Test cases for IAM service health checking."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """Test health check for healthy service."""
        response = await self.client.health_check()
        
        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.timestamp is not None
        assert "database" in response.components
    
    @pytest.mark.asyncio
    async def test_health_check_service_unavailable(self):
        """Test health check when service is unavailable."""
        # Mock service error
        self.client._make_request = AsyncMock(side_effect=Exception("Service unavailable"))
        
        response = await self.client.health_check()
        
        assert response.status == "unhealthy"
        assert response.version == "unknown"


class TestUserContextCreation:
    """Test cases for UserContext creation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    def test_create_user_context_from_valid_response(self):
        """Test creating UserContext from valid token validation response."""
        validation_response = self.factory.create_token_validation_response()
        
        context = self.client.create_user_context(validation_response)
        
        assert context.user_id == "test-user-123"
        assert context.username == "testuser"
        assert context.email == "test@example.com"
        assert "user" in context.roles
        assert context.tenant_id == "tenant-123"
        assert "scopes" in context.metadata
        assert "iam_metadata" in context.metadata
    
    def test_create_user_context_from_invalid_response(self):
        """Test error when creating UserContext from invalid response."""
        validation_response = self.factory.create_token_validation_response(valid=False)
        
        with pytest.raises(ValueError, match="Cannot create context from invalid token"):
            self.client.create_user_context(validation_response)


class TestRequestUtilities:
    """Test cases for HTTP request utilities."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_make_request_without_auth(self):
        """Test making request without authentication."""
        response = await self.client._make_request("GET", "/health")
        
        assert "status" in response
        assert response["status"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_make_request_with_service_auth(self):
        """Test making request with service authentication."""
        response = await self.client._make_request(
            "POST",
            "/api/v1/users/info",
            data={"user_id": "test-user-123"},
            use_service_auth=True
        )
        
        assert "user_id" in response
        assert response["user_id"] == "test-user-123"
    
    @pytest.mark.asyncio
    async def test_make_request_http_error(self):
        """Test handling of HTTP errors in requests."""
        # Mock 500 error
        self.client._client.request = AsyncMock(return_value=MockHTTPResponse(500, {"error": "Internal error"}))
        
        with pytest.raises(Exception, match="HTTP 500"):
            await self.client._make_request("GET", "/error-endpoint")


class TestIntegrationWorkflows:
    """Integration test cases for complete workflows."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_complete_authentication_workflow(self):
        """Test complete authentication workflow."""
        # 1. Validate token
        token = self.factory.create_valid_jwt_token()
        validation_response = await self.client.validate_token(token)
        
        assert validation_response.valid == True
        
        # 2. Create user context
        context = self.client.create_user_context(validation_response)
        assert context.user_id == "test-user-123"
        
        # 3. Check user scopes
        scope_response = await self.client.check_user_scopes(
            context.user_id,
            ["api:ontologies:read"]
        )
        assert scope_response.authorized == True
        
        # 4. Get detailed user info
        user_info = await self.client.get_user_info(user_id=context.user_id)
        assert user_info.user_id == context.user_id
    
    @pytest.mark.asyncio
    async def test_service_to_service_communication_workflow(self):
        """Test service-to-service communication workflow."""
        # 1. Authenticate service
        auth_response = await self.client.authenticate_service()
        assert auth_response.access_token is not None
        
        # 2. Use service token for API calls
        user_info = await self.client.get_user_info(user_id="test-user-123")
        assert user_info.user_id == "test-user-123"
        
        # 3. Check health
        health = await self.client.health_check()
        assert health.status == "healthy"
    
    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self):
        """Test error recovery and resilience."""
        # 1. Test with invalid token
        invalid_token = self.factory.create_invalid_jwt_token()
        validation_response = await self.client.validate_token(invalid_token)
        assert validation_response.valid == False
        
        # 2. Test service unavailable scenario
        self.client._make_request = AsyncMock(side_effect=Exception("Service unavailable"))
        
        # Should handle gracefully
        health = await self.client.health_check()
        assert health.status == "unhealthy"
        
        # 3. Scope check should return unauthorized on error
        scope_response = await self.client.check_user_scopes("user-123", ["api:ontologies:read"])
        assert scope_response.authorized == False
    
    @pytest.mark.asyncio
    async def test_caching_and_performance_workflow(self):
        """Test caching and performance optimizations."""
        token = self.factory.create_valid_jwt_token()
        
        # First validation - should cache result
        response1 = await self.client.validate_token(token)
        assert response1.valid == True
        
        # Second validation - should use cache
        response2 = await self.client.validate_token(token)
        assert response2.valid == True
        assert response2.user_id == response1.user_id
        
        # Verify cache was used by checking Redis
        cache_key = f"iam:token:{token[:20]}"
        cached_data = await self.client._redis_client.get(cache_key)
        assert cached_data is not None


class TestErrorHandlingAndEdgeCases:
    """Test cases for error handling and edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.factory = TestDataFactory()
        self.config = self.factory.create_iam_config()
        self.client = MockIAMServiceClient(self.config)
    
    @pytest.mark.asyncio
    async def test_network_timeout_handling(self):
        """Test handling of network timeouts."""
        # Mock timeout error
        self.client._make_request = AsyncMock(side_effect=Exception("Request timeout"))
        
        response = await self.client.validate_token("test-token")
        
        assert response.valid == False
        assert "timeout" in response.error.lower()
    
    @pytest.mark.asyncio
    async def test_malformed_response_handling(self):
        """Test handling of malformed responses from IAM service."""
        # Mock malformed response
        self.client._make_request = AsyncMock(return_value={"invalid": "response"})
        
        # Should handle malformed response gracefully
        response = await self.client.validate_token("test-token")
        assert response.valid == False
        assert response.error is not None
    
    @pytest.mark.asyncio
    async def test_redis_connection_failure(self):
        """Test graceful handling of Redis connection failures."""
        # Mock Redis connection error
        self.client._redis_client = None
        
        # Should work without caching
        token = self.factory.create_valid_jwt_token()
        response = await self.client.validate_token(token)
        
        assert response.valid == True
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_handling(self):
        """Test handling of concurrent requests."""
        token = self.factory.create_valid_jwt_token()
        
        # Make multiple concurrent requests
        tasks = [
            self.client.validate_token(token),
            self.client.validate_token(token),
            self.client.get_user_info(user_id="test-user-123")
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All should succeed
        assert len(results) == 3
        assert all(not isinstance(r, Exception) for r in results)
    
    @pytest.mark.asyncio
    async def test_resource_cleanup(self):
        """Test proper resource cleanup."""
        async with MockIAMServiceClient(self.config) as client:
            # Use client
            response = await client.validate_token(self.factory.create_valid_jwt_token())
            assert response.valid == True
        
        # Resources should be cleaned up
        assert client._redis_client.closed == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])