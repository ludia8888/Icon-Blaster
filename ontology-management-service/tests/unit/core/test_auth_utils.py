"""Unit tests for authentication utilities."""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from pydantic import ValidationError

from core.auth import UserContext, get_permission_checker


class TestUserContext:
    """Test suite for UserContext model."""
    
    def test_user_context_creation(self):
        """Test creating valid UserContext."""
        context = UserContext(
            user_id="user123",
            username="testuser",
            email="user@example.com",
            tenant_id="tenant456",
            roles=["developer", "reviewer"]
        )
        
        assert context.user_id == "user123"
        assert context.username == "testuser"
        assert context.email == "user@example.com"
        assert context.tenant_id == "tenant456"
        assert context.roles == ["developer", "reviewer"]
        assert context.is_admin is False
    
    def test_user_context_with_minimal_fields(self):
        """Test UserContext with minimal required fields."""
        context = UserContext(
            user_id="user123",
            username="testuser"
        )
        
        assert context.user_id == "user123"
        assert context.username == "testuser"
        assert context.email is None
        assert context.tenant_id is None
        assert context.roles == []
        assert context.is_admin is False
    
    def test_user_context_validation_error(self):
        """Test UserContext validation errors."""
        with pytest.raises(ValidationError):
            UserContext(
                # Missing required username field
                user_id="user123"
            )
    
    def test_user_context_admin_role(self):
        """Test admin role detection."""
        admin_context = UserContext(
            user_id="admin123",
            username="admin",
            roles=["admin", "developer"]
        )
        
        assert admin_context.is_admin is True
        assert admin_context.has_role("admin") is True
        assert admin_context.has_role("developer") is True
    
    def test_user_context_developer_role(self):
        """Test developer role detection."""
        dev_context = UserContext(
            user_id="dev123",
            username="developer",
            roles=["developer"]
        )
        
        assert dev_context.is_developer is True
        assert dev_context.is_admin is False
        assert dev_context.is_reviewer is False
    
    def test_user_context_reviewer_role(self):
        """Test reviewer role detection."""
        reviewer_context = UserContext(
            user_id="rev123",
            username="reviewer",
            roles=["reviewer"]
        )
        
        assert reviewer_context.is_reviewer is True
        assert reviewer_context.is_admin is False
        assert reviewer_context.is_developer is False
    
    def test_user_context_service_account(self):
        """Test service account detection."""
        service_context = UserContext(
            user_id="service123",
            username="service_bot",
            roles=["service_account"]
        )
        
        assert service_context.is_service_account is True
        assert service_context.is_admin is False
    
    def test_has_any_role(self):
        """Test checking for any of multiple roles."""
        context = UserContext(
            user_id="user123",
            username="testuser",
            roles=["developer"]
        )
        
        assert context.has_any_role(["developer", "admin"]) is True
        assert context.has_any_role(["admin", "reviewer"]) is False
    
    def test_has_all_roles(self):
        """Test checking for all roles."""
        context = UserContext(
            user_id="user123",
            username="testuser",
            roles=["developer", "reviewer"]
        )
        
        assert context.has_all_roles(["developer"]) is True
        assert context.has_all_roles(["developer", "reviewer"]) is True
        assert context.has_all_roles(["developer", "reviewer", "admin"]) is False
    
    def test_user_context_with_metadata(self):
        """Test UserContext with metadata."""
        metadata = {"department": "engineering", "level": "senior"}
        context = UserContext(
            user_id="user123",
            username="testuser",
            metadata=metadata
        )
        
        assert context.metadata["department"] == "engineering"
        assert context.metadata["level"] == "senior"
    
    def test_user_context_serialization(self):
        """Test UserContext serialization."""
        context = UserContext(
            user_id="user123",
            username="testuser",
            email="user@example.com",
            tenant_id="tenant456",
            roles=["developer", "reviewer"]
        )
        
        data = context.model_dump()
        assert data["user_id"] == "user123"
        assert data["username"] == "testuser"
        assert data["email"] == "user@example.com"
        assert data["tenant_id"] == "tenant456"
        assert data["roles"] == ["developer", "reviewer"]
    
    def test_user_context_from_dict(self):
        """Test creating UserContext from dictionary."""
        data = {
            "user_id": "user123",
            "username": "testuser",
            "email": "user@example.com",
            "tenant_id": "tenant456",
            "roles": ["developer", "reviewer"]
        }
        
        context = UserContext(**data)
        assert context.user_id == "user123"
        assert context.username == "testuser"
        assert context.email == "user@example.com"
        assert context.tenant_id == "tenant456"
        assert context.roles == ["developer", "reviewer"]


class TestPermissionChecker:
    """Test suite for permission checker functionality."""
    
    def test_get_permission_checker(self):
        """Test getting permission checker instance."""
        checker = get_permission_checker()
        assert checker is not None
        assert hasattr(checker, 'check_permission')
    
    def test_permission_checker_methods(self):
        """Test permission checker has expected methods."""
        checker = get_permission_checker()
        
        # Check that the permission checker has the expected interface
        assert callable(getattr(checker, 'check_permission', None))
        # Note: removed has_permission check as it's not in actual implementation
    
    def test_permission_checker_type(self):
        """Test permission checker type."""
        checker = get_permission_checker()
        assert checker.__class__.__name__ == "PermissionChecker"


class TestAuthenticationFlow:
    """Test suite for authentication flow."""
    
    def test_create_user_context_from_token_data(self):
        """Test creating UserContext from token data."""
        token_data = {
            "sub": "user123",
            "username": "testuser",
            "email": "user@example.com",
            "tenant_id": "tenant456",
            "roles": ["developer", "reviewer"]
        }
        
        # This would typically be done by an authentication service
        context = UserContext(
            user_id=token_data["sub"],
            username=token_data["username"],
            email=token_data.get("email"),
            tenant_id=token_data.get("tenant_id"),
            roles=token_data.get("roles", [])
        )
        
        assert context.user_id == "user123"
        assert context.username == "testuser"
        assert context.email == "user@example.com"
        assert context.tenant_id == "tenant456"
        assert "developer" in context.roles
        assert "reviewer" in context.roles
    
    def test_admin_user_context(self):
        """Test admin user context."""
        admin_context = UserContext(
            user_id="admin123",
            username="admin",
            email="admin@example.com",
            tenant_id="tenant456",
            roles=["admin", "developer"]
        )
        
        assert admin_context.is_admin is True
        assert "admin" in admin_context.roles
        assert admin_context.has_role("admin") is True
    
    def test_user_context_with_custom_roles(self):
        """Test UserContext with custom role structure."""
        roles = [
            "ontology_reader",
            "ontology_writer",
            "branch_creator",
            "schema_validator"
        ]
        
        context = UserContext(
            user_id="user123",
            username="testuser",
            email="user@example.com",
            tenant_id="tenant456",
            roles=roles
        )
        
        assert len(context.roles) == 4
        assert "ontology_reader" in context.roles
        assert "ontology_writer" in context.roles
        assert "branch_creator" in context.roles
        assert "schema_validator" in context.roles
    
    def test_user_context_equality(self):
        """Test UserContext equality comparison."""
        context1 = UserContext(
            user_id="user123",
            username="testuser",
            email="user@example.com",
            tenant_id="tenant456",
            roles=["developer"]
        )
        
        context2 = UserContext(
            user_id="user123",
            username="testuser",
            email="user@example.com",
            tenant_id="tenant456",
            roles=["developer"]
        )
        
        context3 = UserContext(
            user_id="user456",
            username="otheruser",
            email="user2@example.com",
            tenant_id="tenant456",
            roles=["developer"]
        )
        
        assert context1 == context2
        assert context1 != context3
    
    def test_user_context_repr(self):
        """Test UserContext string representation."""
        context = UserContext(
            user_id="user123",
            username="testuser",
            email="user@example.com",
            tenant_id="tenant456",
            roles=["developer", "reviewer"]
        )
        
        repr_str = repr(context)
        assert "user123" in repr_str
        assert "testuser" in repr_str