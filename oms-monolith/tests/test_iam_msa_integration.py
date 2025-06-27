"""
Integration tests for IAM MSA integration
Tests the complete flow without circular dependencies
"""
import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
import httpx

from shared.iam_contracts import (
    IAMScope,
    TokenValidationResponse,
    UserInfoResponse,
    ServiceAuthResponse,
    ScopeCheckResponse
)
from core.integrations.iam_service_client import IAMServiceClient
from core.iam.iam_integration_refactored import IAMIntegration
from core.auth import UserContext
from models.permissions import Role
from middleware.auth_middleware_msa import MSAAuthMiddleware


class TestIAMServiceClient:
    """Test IAM service client functionality"""
    
    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx client"""
        client = AsyncMock()
        return client
    
    @pytest.fixture
    def iam_client(self, mock_httpx_client):
        """Create IAM client with mocked HTTP"""
        client = IAMServiceClient()
        client._client = mock_httpx_client
        return client
    
    @pytest.mark.asyncio
    async def test_validate_token_success(self, iam_client, mock_httpx_client):
        """Test successful token validation"""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "valid": True,
            "user_id": "user123",
            "username": "testuser",
            "email": "test@example.com",
            "scopes": [IAMScope.ONTOLOGIES_READ, IAMScope.SCHEMAS_WRITE],
            "roles": ["developer"],
            "tenant_id": "tenant1",
            "expires_at": "2024-12-31T23:59:59Z"
        }
        mock_httpx_client.request.return_value = mock_response
        
        # Test validation
        response = await iam_client.validate_token("test-token")
        
        assert response.valid is True
        assert response.user_id == "user123"
        assert response.username == "testuser"
        assert IAMScope.ONTOLOGIES_READ in response.scopes
        assert "developer" in response.roles
    
    @pytest.mark.asyncio
    async def test_validate_token_invalid(self, iam_client, mock_httpx_client):
        """Test invalid token validation"""
        # Mock 401 response
        mock_httpx_client.request.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=Mock(),
            response=Mock(status_code=401)
        )
        
        response = await iam_client.validate_token("invalid-token")
        
        assert response.valid is False
        assert response.error == "Invalid or expired token"
    
    @pytest.mark.asyncio
    async def test_get_user_info(self, iam_client, mock_httpx_client):
        """Test getting user information"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "user_id": "user123",
            "username": "testuser",
            "email": "test@example.com",
            "full_name": "Test User",
            "roles": ["developer", "reviewer"],
            "scopes": [IAMScope.ONTOLOGIES_WRITE, IAMScope.PROPOSALS_APPROVE],
            "teams": ["backend", "api"],
            "mfa_enabled": True,
            "active": True,
            "created_at": "2023-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z"
        }
        mock_httpx_client.request.return_value = mock_response
        
        user_info = await iam_client.get_user_info(user_id="user123")
        
        assert user_info is not None
        assert user_info.user_id == "user123"
        assert user_info.mfa_enabled is True
        assert "backend" in user_info.teams
    
    @pytest.mark.asyncio
    async def test_service_authentication(self, iam_client, mock_httpx_client):
        """Test service-to-service authentication"""
        iam_client.config.service_secret = "test-secret"
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "access_token": "service-token-123",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scopes": [IAMScope.SERVICE_ACCOUNT, IAMScope.ONTOLOGIES_READ]
        }
        mock_httpx_client.request.return_value = mock_response
        
        auth_response = await iam_client.authenticate_service()
        
        assert auth_response.access_token == "service-token-123"
        assert auth_response.expires_in == 3600
        assert IAMScope.SERVICE_ACCOUNT in auth_response.scopes


class TestIAMIntegration:
    """Test refactored IAM integration"""
    
    @pytest.fixture
    def mock_iam_client(self):
        """Mock IAM client"""
        client = AsyncMock()
        return client
    
    @pytest.fixture
    def iam_integration(self, mock_iam_client):
        """Create IAM integration with mocked client"""
        integration = IAMIntegration()
        integration.client = mock_iam_client
        return integration
    
    @pytest.mark.asyncio
    async def test_validate_jwt_enhanced(self, iam_integration, mock_iam_client):
        """Test enhanced JWT validation"""
        # Mock validation response
        mock_iam_client.validate_token.return_value = TokenValidationResponse(
            valid=True,
            user_id="user123",
            username="testuser",
            email="test@example.com",
            scopes=[
                IAMScope.ONTOLOGIES_WRITE,
                IAMScope.SCHEMAS_READ,
                IAMScope.PROPOSALS_WRITE
            ],
            roles=["existing_role"],
            tenant_id="tenant1"
        )
        
        # Test validation
        user_context = await iam_integration.validate_jwt_enhanced("test-token")
        
        assert user_context.user_id == "user123"
        assert user_context.username == "testuser"
        
        # Check role mapping from scopes
        assert "developer" in user_context.roles  # Should be mapped from scopes
        assert "existing_role" in user_context.roles  # Should keep existing roles
        
        # Check scopes in metadata
        assert IAMScope.ONTOLOGIES_WRITE in user_context.metadata["scopes"]
    
    @pytest.mark.asyncio
    async def test_scope_checking(self, iam_integration):
        """Test scope checking methods"""
        user_context = UserContext(
            user_id="user123",
            username="testuser",
            roles=["developer"],
            metadata={
                "scopes": [
                    IAMScope.ONTOLOGIES_READ,
                    IAMScope.SCHEMAS_WRITE,
                    IAMScope.BRANCHES_READ
                ]
            }
        )
        
        # Test single scope check
        assert iam_integration.check_scope(user_context, IAMScope.ONTOLOGIES_READ) is True
        assert iam_integration.check_scope(user_context, IAMScope.ONTOLOGIES_ADMIN) is False
        
        # Test any scope check
        assert iam_integration.check_any_scope(
            user_context,
            [IAMScope.ONTOLOGIES_ADMIN, IAMScope.SCHEMAS_WRITE]
        ) is True
        
        # Test all scopes check
        assert iam_integration.check_all_scopes(
            user_context,
            [IAMScope.ONTOLOGIES_READ, IAMScope.BRANCHES_READ]
        ) is True
        assert iam_integration.check_all_scopes(
            user_context,
            [IAMScope.ONTOLOGIES_READ, IAMScope.ONTOLOGIES_ADMIN]
        ) is False
    
    def test_get_required_scopes(self, iam_integration):
        """Test getting required scopes for resources"""
        # Schema operations
        scopes = iam_integration.get_required_scopes("schema", "read")
        assert IAMScope.SCHEMAS_READ in scopes
        
        scopes = iam_integration.get_required_scopes("schema", "create")
        assert IAMScope.SCHEMAS_WRITE in scopes
        
        # Object type operations
        scopes = iam_integration.get_required_scopes("object_type", "delete")
        assert IAMScope.ONTOLOGIES_WRITE in scopes
        
        # Proposal operations
        scopes = iam_integration.get_required_scopes("proposal", "approve")
        assert IAMScope.PROPOSALS_APPROVE in scopes


class TestMSAAuthMiddleware:
    """Test MSA authentication middleware"""
    
    @pytest.fixture
    def mock_request(self):
        """Create mock request"""
        request = Mock()
        request.url.path = "/api/v1/schemas/main/object-types"
        request.method = "GET"
        request.headers = {"Authorization": "Bearer test-token"}
        request.state = Mock()
        return request
    
    @pytest.fixture
    def middleware(self):
        """Create middleware instance"""
        app = Mock()
        return MSAAuthMiddleware(app)
    
    @pytest.mark.asyncio
    async def test_public_path_bypass(self, middleware, mock_request):
        """Test that public paths bypass authentication"""
        mock_request.url.path = "/health"
        
        call_next = AsyncMock()
        call_next.return_value = Mock(headers={})
        
        response = await middleware.dispatch(mock_request, call_next)
        
        # Should not have user in state
        assert mock_request.state.user is None
        call_next.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_successful_authentication(self, middleware, mock_request):
        """Test successful authentication flow"""
        # Mock IAM integration
        mock_user_context = UserContext(
            user_id="user123",
            username="testuser",
            roles=["developer"],
            metadata={"scopes": [IAMScope.SCHEMAS_READ]}
        )
        
        with patch.object(middleware.iam_integration, 'validate_jwt_enhanced') as mock_validate:
            mock_validate.return_value = mock_user_context
            
            call_next = AsyncMock()
            mock_response = Mock()
            mock_response.headers = {}
            call_next.return_value = mock_response
            
            response = await middleware.dispatch(mock_request, call_next)
            
            # Should set user in state
            assert mock_request.state.user == mock_user_context
            
            # Should add headers
            assert response.headers["X-User-ID"] == "user123"
            assert response.headers["X-Auth-Method"] == "iam-msa"
    
    @pytest.mark.asyncio
    async def test_missing_token(self, middleware, mock_request):
        """Test handling of missing token"""
        mock_request.headers = {}  # No Authorization header
        
        call_next = AsyncMock()
        
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await middleware.dispatch(mock_request, call_next)
        
        assert exc_info.value.response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_scope_validation(self, middleware, mock_request):
        """Test endpoint scope validation"""
        mock_request.url.path = "/api/v1/schemas/main/object-types"
        mock_request.method = "POST"  # Requires write scope
        
        # User has only read scope
        mock_user_context = UserContext(
            user_id="user123",
            username="testuser",
            roles=["viewer"],
            metadata={"scopes": [IAMScope.SCHEMAS_READ]}
        )
        
        with patch.object(middleware.iam_integration, 'validate_jwt_enhanced') as mock_validate:
            mock_validate.return_value = mock_user_context
            
            call_next = AsyncMock()
            
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await middleware.dispatch(mock_request, call_next)
            
            assert exc_info.value.response.status_code == 403


class TestCircularDependencyResolution:
    """Test that circular dependencies are resolved"""
    
    def test_no_circular_imports(self):
        """Test that imports don't create circular dependencies"""
        # These imports should not raise ImportError
        from models.scope_role_mapping import ScopeRoleMatrix
        from shared.iam_contracts import IAMScope
        from core.iam.iam_integration_refactored import IAMIntegration
        
        # Should be able to use all components
        scopes = [IAMScope.ONTOLOGIES_WRITE, IAMScope.SCHEMAS_READ]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        assert Role.DEVELOPER in roles
        
        # IAM integration should work
        integration = IAMIntegration()
        assert integration is not None
    
    def test_scope_role_mapping_independence(self):
        """Test that scope role mapping works independently"""
        from models.scope_role_mapping import ScopeRoleMatrix
        
        # Test role to scope mapping
        scopes = ScopeRoleMatrix.get_scopes_for_role(Role.ADMIN)
        assert IAMScope.SYSTEM_ADMIN in scopes
        
        # Test scope to role mapping
        roles = ScopeRoleMatrix.get_role_for_scopes([IAMScope.PROPOSALS_APPROVE])
        assert Role.REVIEWER in roles
    
    def test_iam_contracts_standalone(self):
        """Test that IAM contracts are standalone"""
        from shared.iam_contracts import (
            TokenValidationRequest,
            TokenValidationResponse,
            SCOPE_HIERARCHY
        )
        
        # Should be able to create DTOs
        request = TokenValidationRequest(token="test-token")
        assert request.token == "test-token"
        
        # Hierarchy should be accessible
        assert IAMScope.SYSTEM_ADMIN in SCOPE_HIERARCHY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])