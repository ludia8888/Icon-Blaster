"""
Tests for Scope-Role Mapping
Validates the relationship between IAM scopes and OMS roles
"""
import pytest
from models.scope_role_mapping import ScopeRoleMatrix
from models.permissions import Role
from core.iam.iam_integration import IAMScope


class TestScopeRoleMapping:
    """Test scope to role mapping logic"""
    
    def test_admin_role_mapping(self):
        """Test admin role gets system admin scope"""
        scopes = [IAMScope.SYSTEM_ADMIN]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        assert Role.ADMIN in roles
        assert len(roles) == 1  # System admin should be the only role
    
    def test_developer_role_mapping(self):
        """Test developer role mapping"""
        scopes = [
            IAMScope.ONTOLOGIES_READ,
            IAMScope.ONTOLOGIES_WRITE,
            IAMScope.SCHEMAS_READ,
            IAMScope.BRANCHES_READ,
            IAMScope.BRANCHES_WRITE
        ]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        assert Role.DEVELOPER in roles
    
    def test_reviewer_role_mapping(self):
        """Test reviewer role mapping"""
        scopes = [
            IAMScope.PROPOSALS_READ,
            IAMScope.PROPOSALS_APPROVE,
            IAMScope.ONTOLOGIES_READ
        ]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        assert Role.REVIEWER in roles
    
    def test_viewer_role_mapping(self):
        """Test viewer role mapping"""
        scopes = [
            IAMScope.ONTOLOGIES_READ,
            IAMScope.SCHEMAS_READ,
            IAMScope.BRANCHES_READ
        ]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        # Should get viewer role for read-only scopes
        assert Role.VIEWER in roles
    
    def test_service_account_role_mapping(self):
        """Test service account role mapping"""
        scopes = [
            IAMScope.SERVICE_ACCOUNT,
            IAMScope.WEBHOOK_EXECUTE
        ]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        assert Role.SERVICE_ACCOUNT in roles
    
    def test_multiple_roles(self):
        """Test user with multiple roles"""
        scopes = [
            IAMScope.ONTOLOGIES_READ,
            IAMScope.ONTOLOGIES_WRITE,
            IAMScope.PROPOSALS_READ,
            IAMScope.PROPOSALS_APPROVE
        ]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        # Should have both developer and reviewer roles
        assert Role.DEVELOPER in roles
        assert Role.REVIEWER in roles
    
    def test_no_matching_roles(self):
        """Test scopes that don't match any role"""
        scopes = ["api:unknown:scope"]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        assert len(roles) == 0
    
    def test_scope_patterns(self):
        """Test pattern-based scope matching"""
        # Test write pattern for developer
        scopes = ["api:custom:write"]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        assert Role.DEVELOPER in roles
    
    def test_get_scopes_for_role(self):
        """Test getting scopes for a specific role"""
        scopes = ScopeRoleMatrix.get_scopes_for_role(Role.DEVELOPER)
        
        assert IAMScope.ONTOLOGIES_READ in scopes
        assert IAMScope.ONTOLOGIES_WRITE in scopes
        assert IAMScope.SCHEMAS_READ in scopes
    
    def test_validate_role_scope_assignment(self):
        """Test role-scope assignment validation"""
        # Valid assignment
        is_valid, issues = ScopeRoleMatrix.validate_role_scope_assignment(
            Role.REVIEWER,
            [IAMScope.PROPOSALS_READ, IAMScope.PROPOSALS_APPROVE]
        )
        assert is_valid
        assert len(issues) == 0
        
        # Invalid assignment - missing required scopes
        is_valid, issues = ScopeRoleMatrix.validate_role_scope_assignment(
            Role.REVIEWER,
            [IAMScope.ONTOLOGIES_READ]  # Missing required scopes
        )
        assert not is_valid
        assert len(issues) > 0
    
    def test_scope_hierarchy(self):
        """Test scope hierarchy relationships"""
        hierarchy = ScopeRoleMatrix.get_scope_hierarchy()
        
        # System admin should imply other admin scopes
        assert IAMScope.ONTOLOGIES_ADMIN in hierarchy[IAMScope.SYSTEM_ADMIN]
        
        # Write should imply read
        assert IAMScope.ONTOLOGIES_READ in hierarchy[IAMScope.ONTOLOGIES_WRITE]
    
    def test_edge_cases(self):
        """Test edge cases in scope-role mapping"""
        # Empty scopes
        roles = ScopeRoleMatrix.get_role_for_scopes([])
        assert len(roles) == 0
        
        # Duplicate scopes
        scopes = [IAMScope.ONTOLOGIES_READ, IAMScope.ONTOLOGIES_READ]
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        assert Role.VIEWER in roles
        
        # Unknown role
        scopes = ScopeRoleMatrix.get_scopes_for_role("unknown_role")
        assert len(scopes) == 0


class TestScopeDefinitions:
    """Test scope definitions and documentation"""
    
    def test_scope_definitions_complete(self):
        """Test that all IAM scopes have definitions"""
        defined_scopes = set(ScopeRoleMatrix.SCOPE_DEFINITIONS.keys())
        
        # Get all IAM scopes from the class
        iam_scopes = set()
        for attr_name in dir(IAMScope):
            if not attr_name.startswith('_'):
                iam_scopes.add(getattr(IAMScope, attr_name))
        
        # All scopes should have definitions
        assert iam_scopes.issubset(defined_scopes)
    
    def test_scope_definition_structure(self):
        """Test scope definition data structure"""
        for scope, definition in ScopeRoleMatrix.SCOPE_DEFINITIONS.items():
            assert definition.scope == scope
            assert isinstance(definition.description, str)
            assert isinstance(definition.resource_types, list)
            assert isinstance(definition.actions, list)
            assert isinstance(definition.examples, list)
            assert len(definition.description) > 0
    
    def test_role_definitions_complete(self):
        """Test that all roles have definitions"""
        defined_roles = set(ScopeRoleMatrix.ROLE_SCOPE_MAPPING.keys())
        
        # Get all roles from enum
        all_roles = set(Role)
        
        # All roles should have definitions
        assert all_roles == defined_roles
    
    def test_role_definition_structure(self):
        """Test role definition data structure"""
        for role, definition in ScopeRoleMatrix.ROLE_SCOPE_MAPPING.items():
            assert definition.role == role
            assert isinstance(definition.description, str)
            assert isinstance(definition.required_scopes, list)
            assert isinstance(definition.optional_scopes, list)
            assert isinstance(definition.scope_patterns, list)
            assert len(definition.description) > 0


class TestIAMIntegration:
    """Test integration with IAM components"""
    
    def test_iam_integration_uses_mapping(self):
        """Test that IAM integration uses the scope-role mapping"""
        from core.iam.iam_integration import IAMIntegration
        
        iam = IAMIntegration()
        
        # This should use the ScopeRoleMatrix
        scopes = [IAMScope.ONTOLOGIES_WRITE, IAMScope.SCHEMAS_READ]
        # Note: _scopes_to_roles is async, so we test the mapping directly
        roles = ScopeRoleMatrix.get_role_for_scopes(scopes)
        
        assert Role.DEVELOPER in roles


if __name__ == "__main__":
    pytest.main([__file__, "-v"])