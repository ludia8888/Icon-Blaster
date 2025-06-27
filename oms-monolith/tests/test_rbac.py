"""
RBAC (Role-Based Access Control) Tests
Comprehensive test suite for permission checking and middleware
"""
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from core.auth import UserContext, get_permission_checker
from models.permissions import Role, ResourceType, Action, PermissionChecker
from middleware.rbac_middleware import RBACMiddleware
from core.integrations.user_service_client import create_mock_jwt


class TestPermissionChecker:
    """Test the PermissionChecker class"""
    
    def setup_method(self):
        self.checker = PermissionChecker()
    
    def test_admin_has_all_permissions(self):
        """Admin should have all permissions"""
        # Test various resources and actions
        assert self.checker.check_permission(
            ["admin"], ResourceType.SCHEMA.value, Action.CREATE.value
        )
        assert self.checker.check_permission(
            ["admin"], ResourceType.OBJECT_TYPE.value, Action.DELETE.value
        )
        assert self.checker.check_permission(
            ["admin"], ResourceType.PROPOSAL.value, Action.APPROVE.value
        )
        assert self.checker.check_permission(
            ["admin"], ResourceType.BRANCH.value, Action.MERGE.value
        )
    
    def test_developer_permissions(self):
        """Developer should have specific permissions"""
        # Can create and update most resources
        assert self.checker.check_permission(
            ["developer"], ResourceType.OBJECT_TYPE.value, Action.CREATE.value
        )
        assert self.checker.check_permission(
            ["developer"], ResourceType.LINK_TYPE.value, Action.UPDATE.value
        )
        assert self.checker.check_permission(
            ["developer"], ResourceType.BRANCH.value, Action.CREATE.value
        )
        
        # Cannot delete critical resources
        assert not self.checker.check_permission(
            ["developer"], ResourceType.SCHEMA.value, Action.DELETE.value
        )
        
        # Cannot approve proposals
        assert not self.checker.check_permission(
            ["developer"], ResourceType.PROPOSAL.value, Action.APPROVE.value
        )
    
    def test_reviewer_permissions(self):
        """Reviewer should have read and approval permissions"""
        # Can read everything
        assert self.checker.check_permission(
            ["reviewer"], ResourceType.SCHEMA.value, Action.READ.value
        )
        assert self.checker.check_permission(
            ["reviewer"], ResourceType.OBJECT_TYPE.value, Action.READ.value
        )
        
        # Can approve/reject proposals
        assert self.checker.check_permission(
            ["reviewer"], ResourceType.PROPOSAL.value, Action.APPROVE.value
        )
        assert self.checker.check_permission(
            ["reviewer"], ResourceType.PROPOSAL.value, Action.REJECT.value
        )
        
        # Cannot create or update
        assert not self.checker.check_permission(
            ["reviewer"], ResourceType.OBJECT_TYPE.value, Action.CREATE.value
        )
    
    def test_viewer_permissions(self):
        """Viewer should have read-only permissions"""
        # Can read
        assert self.checker.check_permission(
            ["viewer"], ResourceType.SCHEMA.value, Action.READ.value
        )
        assert self.checker.check_permission(
            ["viewer"], ResourceType.AUDIT.value, Action.READ.value
        )
        
        # Cannot write
        assert not self.checker.check_permission(
            ["viewer"], ResourceType.OBJECT_TYPE.value, Action.CREATE.value
        )
        assert not self.checker.check_permission(
            ["viewer"], ResourceType.BRANCH.value, Action.UPDATE.value
        )
    
    def test_service_account_permissions(self):
        """Service account should have specific system permissions"""
        # Can read schemas and execute webhooks
        assert self.checker.check_permission(
            ["service_account"], ResourceType.SCHEMA.value, Action.READ.value
        )
        assert self.checker.check_permission(
            ["service_account"], ResourceType.WEBHOOK.value, Action.EXECUTE.value
        )
        
        # Can create audit logs
        assert self.checker.check_permission(
            ["service_account"], ResourceType.AUDIT.value, Action.CREATE.value
        )
        
        # Cannot modify schemas
        assert not self.checker.check_permission(
            ["service_account"], ResourceType.OBJECT_TYPE.value, Action.UPDATE.value
        )
    
    def test_multiple_roles(self):
        """User with multiple roles should have combined permissions"""
        # Developer + Reviewer
        roles = ["developer", "reviewer"]
        
        # Has developer permissions
        assert self.checker.check_permission(
            roles, ResourceType.OBJECT_TYPE.value, Action.CREATE.value
        )
        
        # Also has reviewer permissions
        assert self.checker.check_permission(
            roles, ResourceType.PROPOSAL.value, Action.APPROVE.value
        )
    
    def test_invalid_role(self):
        """Invalid role should not grant any permissions"""
        assert not self.checker.check_permission(
            ["invalid_role"], ResourceType.SCHEMA.value, Action.READ.value
        )
    
    def test_invalid_resource_or_action(self):
        """Invalid resource or action should return False"""
        assert not self.checker.check_permission(
            ["admin"], "invalid_resource", Action.READ.value
        )
        assert not self.checker.check_permission(
            ["admin"], ResourceType.SCHEMA.value, "invalid_action"
        )


class TestRBACMiddleware:
    """Test the RBAC Middleware"""
    
    @pytest.fixture
    def app(self):
        """Create test FastAPI app with RBAC middleware"""
        app = FastAPI()
        
        # Add RBAC middleware
        app.add_middleware(RBACMiddleware)
        
        # Test endpoints
        @app.get("/api/v1/schemas/{branch}/object-types")
        async def get_object_types(branch: str):
            return {"object_types": []}
        
        @app.post("/api/v1/schemas/{branch}/object-types")
        async def create_object_type(branch: str):
            return {"created": True}
        
        @app.post("/api/v1/proposals/{proposal_id}/approve")
        async def approve_proposal(proposal_id: str):
            return {"approved": True}
        
        @app.get("/health")
        async def health():
            return {"status": "ok"}
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client"""
        return TestClient(app)
    
    def test_public_endpoint_no_auth(self, client):
        """Public endpoints should be accessible without auth"""
        response = client.get("/health")
        assert response.status_code == 200
    
    def test_protected_endpoint_no_auth(self, client):
        """Protected endpoints should return 401 without auth"""
        response = client.get("/api/v1/schemas/main/object-types")
        assert response.status_code == 401
    
    @patch('middleware.rbac_middleware.RBACMiddleware._match_route')
    def test_developer_can_read_object_types(self, mock_match, client, app):
        """Developer should be able to read object types"""
        # Mock the route matching
        mock_match.return_value = (ResourceType.OBJECT_TYPE, Action.READ)
        
        # Create mock request with developer user
        with client as c:
            # Inject user context
            request = Mock(spec=Request)
            request.state = Mock()
            request.state.user = UserContext(
                user_id="dev1",
                username="developer1",
                email="dev1@example.com",
                roles=["developer"]
            )
            request.method = "GET"
            request.url = Mock()
            request.url.path = "/api/v1/schemas/main/object-types"
            
            # Simulate middleware behavior
            checker = get_permission_checker()
            assert checker.check_permission(
                ["developer"],
                ResourceType.OBJECT_TYPE.value,
                Action.READ.value
            )
    
    @patch('middleware.rbac_middleware.RBACMiddleware._match_route')
    def test_developer_cannot_approve_proposal(self, mock_match, client):
        """Developer should not be able to approve proposals"""
        mock_match.return_value = (ResourceType.PROPOSAL, Action.APPROVE)
        
        # Create mock request with developer user
        request = Mock(spec=Request)
        request.state = Mock()
        request.state.user = UserContext(
            user_id="dev1",
            username="developer1",
            email="dev1@example.com",
            roles=["developer"]
        )
        
        # Check permission
        checker = get_permission_checker()
        assert not checker.check_permission(
            ["developer"],
            ResourceType.PROPOSAL.value,
            Action.APPROVE.value
        )
    
    def test_jwt_token_validation(self):
        """Test JWT token creation and validation"""
        # Create tokens with different roles
        admin_token = create_mock_jwt(
            user_id="admin1",
            username="admin_user",
            roles=["admin"]
        )
        
        developer_token = create_mock_jwt(
            user_id="dev1",
            username="dev_user",
            roles=["developer"]
        )
        
        # Tokens should be different
        assert admin_token != developer_token
        
        # Decode and verify
        import jwt
        admin_payload = jwt.decode(
            admin_token,
            "your-secret-key",
            algorithms=["HS256"]
        )
        assert admin_payload["roles"] == ["admin"]
        assert admin_payload["username"] == "admin_user"


class TestUserContext:
    """Test UserContext model"""
    
    def test_role_helpers(self):
        """Test role helper methods"""
        user = UserContext(
            user_id="user1",
            username="testuser",
            email="testuser@example.com",
            roles=["developer", "reviewer"]
        )
        
        assert not user.is_admin
        assert user.is_developer
        assert user.is_reviewer
        assert not user.is_service_account
        
        assert user.has_role("developer")
        assert user.has_any_role(["admin", "developer"])
        assert user.has_all_roles(["developer", "reviewer"])
        assert not user.has_all_roles(["developer", "admin"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])